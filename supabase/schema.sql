
create extension if not exists "uuid-ossp";

create table if not exists users (
  id uuid primary key default uuid_generate_v4(),
  email text unique not null,
  password text not null,
  first_name text,
  last_name text,
  role text not null default 'user',
  status text not null default 'pending',
  verified boolean not null default false,
  joined timestamptz not null default now()
);

create table if not exists settings (
  id uuid primary key default uuid_generate_v4(),
  entry_code text not null default '1234'
);

create table if not exists videos (
  id text primary key,
  title text not null,
  genre text,
  meta text,
  episode text,
  src text not null,
  is_stream boolean not null default true,
  is_youtube boolean not null default false,
  sub_data text,
  created_at timestamptz not null default now()
);

create table if not exists pending_verifications (
  id uuid primary key default uuid_generate_v4(),
  first_name text not null,
  last_name text,
  email text not null,
  password text not null,
  code text not null,
  created_at timestamptz not null default now()
);
