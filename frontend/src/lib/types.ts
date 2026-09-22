export type Spec = [string, string, string];
export type PartField = [string, string, string, boolean, boolean];
export interface Fact {
  id: string;
  field: string;
  value: string;
  origin?: string;
  review_status?: string;
  verification_status?: string;
  evidence?: { url: string; note: string }[];
  reason?: string;
  identifier?: Record<string, unknown> | null;
}
export interface Profile {
  schema_version?: number;
  facts: Fact[];
  rejected?: string[];
}
export interface Car {
  id: string;
  name: string;
  specs: Record<string, string>;
  photo_ids?: string[];
}
export interface Order {
  id: string;
  description: string;
  vehicle: string;
  created_at: string;
  photo_count?: number;
  cover_id?: string;
  latest_status?: string;
  car_id?: string;
  part_profile: Profile;
  profile_revision: number;
}
export interface Listing {
  url: string;
  title: string;
  image_url?: string;
  price?: string;
  shipping_cost?: string;
  description?: string;
  seller?: string;
  location?: string;
  condition?: string;
  pickup?: string;
  shipping?: string;
  availability?: string;
  found_at?: string;
  compatibility?: string;
  variant_checks?: string;
  visual_status?: string;
  visual_comparison?: string;
  availability_evidence?: string;
  provider?: string;
}
export interface Research {
  sources?: string[];
  remote_url?: string;
  description?: string;
  vehicle?: string;
  car_profile?: Record<string, string>;
  id: string;
  status: string;
  provider: string;
  model: string;
  created_at: string;
  result: string;
  error?: string;
  listings?: Listing[];
  part_profile?: Profile;
  language_preferences?: {
    response_language: string;
    search_languages: string[];
  };
  research_meta?: {
    current_round: number;
    max_rounds: number;
    rounds: {
      number: number;
      new_listings: number;
      filtered_listings: number;
      status: string;
      remote_url?: string;
    }[];
    new_listings: number;
    stop_reason?: string;
    reported_tokens: number;
    usage_complete: boolean;
  };
  reasoning_effort?: string;
  instructions?: string;
  preferred_options?: number;
  preferred_price?: string;
  pickup_areas?: string;
  shipping_areas?: string;
  priority_websites?: string[];
  web_search_observed?: boolean;
  schedule_id?: string;
}
export interface Schedule {
  id: string;
  weekday: number;
  local_time: string;
  enabled: boolean;
  discord_notify: boolean;
  next_run: string;
  last_message?: string;
  settings: Record<string, string | number | string[]>;
}
export interface PagePayload {
  nonce?: string;
  page: string;
  data: unknown;
  csrf: string;
  messages: string[];
  path: string;
}
