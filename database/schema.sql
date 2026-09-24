-- ============================================================================
-- Health RAG Chatbot — Supabase schema (PRD sections 13, 20, 22, 28)
-- Run in the Supabase SQL editor. Requires the `vector` extension (pgvector).
-- ============================================================================

create extension if not exists vector;
create extension if not exists "uuid-ossp";

-- ----------------------------------------------------------------------------
-- Users (mirrors auth.users; profile row)
-- ----------------------------------------------------------------------------
create table if not exists public.users (
    id uuid primary key references auth.users (id) on delete cascade,
    email text,
    created_at timestamptz default now()
);

-- ----------------------------------------------------------------------------
-- Conversations
-- ----------------------------------------------------------------------------
create table if not exists public.conversations (
    id uuid primary key default uuid_generate_v4(),
    user_id uuid references public.users (id) on delete cascade,
    status text default 'active',
    risk_level text default 'unknown',
    started_at timestamptz default now(),
    ended_at timestamptz
);

-- ----------------------------------------------------------------------------
-- Messages
-- ----------------------------------------------------------------------------
create table if not exists public.messages (
    id uuid primary key default uuid_generate_v4(),
    conversation_id uuid references public.conversations (id) on delete cascade,
    role text not null check (role in ('user', 'assistant', 'system')),
    content text not null,
    created_at timestamptz default now()
);
create index if not exists idx_messages_conversation on public.messages (conversation_id);

-- ----------------------------------------------------------------------------
-- Assessments (structured conversation state)
-- ----------------------------------------------------------------------------
create table if not exists public.assessments (
    id uuid primary key default uuid_generate_v4(),
    conversation_id uuid references public.conversations (id) on delete cascade,
    symptoms jsonb default '[]'::jsonb,
    risk_level text default 'unknown',
    recommendation text,
    possible_explanations jsonb default '[]'::jsonb,
    red_flags jsonb default '[]'::jsonb,
    status text default 'active',
    created_at timestamptz default now()
);
create index if not exists idx_assessments_conversation on public.assessments (conversation_id);

-- ----------------------------------------------------------------------------
-- Medical knowledge base (PRD sections 13, 30)
-- ----------------------------------------------------------------------------
create table if not exists public.medical_documents (
    id uuid primary key default uuid_generate_v4(),
    title text not null,
    source text,
    source_url text,
    category text,
    content text,
    metadata jsonb default '{}'::jsonb,
    version text,
    -- Document lifecycle: DRAFT, UNDER_REVIEW, APPROVED, PUBLISHED, DEPRECATED
    status text default 'DRAFT',
    reviewed_at timestamptz,
    created_at timestamptz default now()
);

-- Embedding dimension defaults to 1536 (OpenAI text-embedding-3-small). Adjust
-- to match your embedding model, and keep it in sync with EMBEDDING_DIMENSIONS.
create table if not exists public.medical_chunks (
    id uuid primary key default uuid_generate_v4(),
    document_id uuid references public.medical_documents (id) on delete cascade,
    content text not null,
    embedding vector(1536),
    metadata jsonb default '{}'::jsonb,
    created_at timestamptz default now()
);

-- Approximate-nearest-neighbor index for cosine distance.
create index if not exists idx_medical_chunks_embedding
    on public.medical_chunks
    using ivfflat (embedding vector_cosine_ops)
    with (lists = 100);

-- ----------------------------------------------------------------------------
-- Medical report uploads (analysis pipeline mirrors symptom triage)
-- Raw file bytes go to Supabase Storage bucket `medical-reports`; storage_path
-- points there. NOTE: the Storage bucket itself must be created manually in the
-- Supabase dashboard (Storage > New bucket) — SQL cannot create Storage buckets.
-- ----------------------------------------------------------------------------
create table if not exists public.report_documents (
    id uuid primary key default uuid_generate_v4(),
    conversation_id uuid references public.conversations (id) on delete cascade,
    filename text not null,
    content_type text,
    storage_path text,
    extracted_text text,
    analysis jsonb default '{}'::jsonb,
    risk_level text default 'unknown',
    status text default 'completed',
    created_at timestamptz default now()
);
create index if not exists idx_report_documents_conversation
    on public.report_documents (conversation_id);

-- ----------------------------------------------------------------------------
-- Feedback
-- ----------------------------------------------------------------------------
create table if not exists public.feedback (
    id uuid primary key default uuid_generate_v4(),
    conversation_id uuid references public.conversations (id) on delete cascade,
    rating int check (rating between 1 and 5),
    feedback_text text,
    created_at timestamptz default now()
);

-- ----------------------------------------------------------------------------
-- Vector search RPC (called by the backend via supabase.rpc)
-- Only APPROVED / PUBLISHED documents are eligible (PRD section 30).
-- ----------------------------------------------------------------------------
create or replace function public.match_medical_chunks (
    query_embedding vector(1536),
    match_count int default 5,
    filter_category text default null
)
returns table (
    id uuid,
    document_id uuid,
    content text,
    metadata jsonb,
    score float
)
language sql stable
as $$
    select
        c.id,
        c.document_id,
        c.content,
        c.metadata,
        1 - (c.embedding <=> query_embedding) as score
    from public.medical_chunks c
    join public.medical_documents d on d.id = c.document_id
    where d.status in ('APPROVED', 'PUBLISHED')
      and (filter_category is null or c.metadata ->> 'category' = filter_category)
    order by c.embedding <=> query_embedding
    limit match_count;
$$;

-- ============================================================================
-- Row Level Security (PRD sections 22, 28)
-- Users may only access their own conversations / messages / assessments.
-- The knowledge base is read-only to clients; writes require the service role.
-- ============================================================================
alter table public.users enable row level security;
alter table public.conversations enable row level security;
alter table public.messages enable row level security;
alter table public.assessments enable row level security;
alter table public.feedback enable row level security;
alter table public.medical_documents enable row level security;
alter table public.medical_chunks enable row level security;
alter table public.report_documents enable row level security;

-- Users: self only
create policy "users_select_self" on public.users
    for select using (auth.uid() = id);

-- Conversations: owner only
create policy "conversations_owner" on public.conversations
    for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- Messages: via owning conversation
create policy "messages_owner" on public.messages
    for all using (
        exists (
            select 1 from public.conversations c
            where c.id = messages.conversation_id and c.user_id = auth.uid()
        )
    );

-- Assessments: via owning conversation
create policy "assessments_owner" on public.assessments
    for all using (
        exists (
            select 1 from public.conversations c
            where c.id = assessments.conversation_id and c.user_id = auth.uid()
        )
    );

-- Feedback: via owning conversation
create policy "feedback_owner" on public.feedback
    for all using (
        exists (
            select 1 from public.conversations c
            where c.id = feedback.conversation_id and c.user_id = auth.uid()
        )
    );

-- Report documents: via owning conversation
create policy "report_documents_owner" on public.report_documents
    for all using (
        exists (
            select 1 from public.conversations c
            where c.id = report_documents.conversation_id and c.user_id = auth.uid()
        )
    );

-- Knowledge base: readable by any authenticated user; only PUBLISHED/APPROVED.
create policy "medical_documents_read" on public.medical_documents
    for select using (status in ('APPROVED', 'PUBLISHED'));
create policy "medical_chunks_read" on public.medical_chunks
    for select using (true);

-- NOTE: The backend uses the service-role key, which bypasses RLS. Keep that key
-- server-side only. Client-side Supabase access must use the anon key so these
-- policies are enforced.
