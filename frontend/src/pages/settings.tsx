import {
  Globe2,
  MessageSquare,
  RefreshCw,
  Save,
  Sparkles,
  Terminal,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  CheckField,
  Empty,
  Field,
  FormChoice,
  Heading,
  Notice,
  PostForm,
  Section,
  Status,
} from "@/components/shared";
import { usePage, date } from "@/lib/page";
export function Sources() {
  const { data: d } = usePage<{ urls: string; error?: string }>();
  return (
    <>
      <Heading
        title="Search sources"
        description="Start in the right places. Let AI explore from there."
      />
      <div className="form-layout">
        <div>
          {d.error && <Notice error>{d.error}</Notice>}
          <Section
            title="Priority websites"
            description="Checked in order before searching the wider web."
            action={<Globe2 size={20} />}
          >
            <PostForm>
              <Field
                name="urls"
                label="Websites, in priority order"
                textarea
                rows={10}
                maxLength={65000}
                defaultValue={d.urls}
                spellCheck={false}
                placeholder="https://www.example.com"
                help="One public website per line. Up to 30 websites. Move a line up to check it sooner."
              />
              <Button type="submit">
                <Save size={16} />
                Save websites
              </Button>
            </PostForm>
          </Section>
        </div>
        <aside className="form-aside">
          <Globe2 size={25} />
          <h2>Priority sources</h2>
          <p>
            Add specialist suppliers, local marketplaces and parts catalogues
            you trust.
          </p>
          <p>
            Applies to new searches with Codex and Open WebUI. Re-save existing
            schedules to update their sources.
          </p>
        </aside>
      </div>
    </>
  );
}
export function Preferences() {
  const { data: d } = usePage<{
    preferences: { response_language: string; search_languages: string[] };
    languages: Record<string, string>;
    error?: string;
  }>();
  return (
    <>
      <Heading
        title="Preferences"
        description="Choose how AI describes your parts and searches for them."
      />
      <PostForm className="settings-width">
        {d.error && <Notice error>{d.error}</Notice>}
        <Section
          title="AI response language"
          description="Used for descriptions, explanations and questions."
        >
          <FormChoice
            name="response_language"
            label="Response language"
            defaultValue={d.preferences.response_language}
            options={Object.entries(d.languages).map(([value, label]) => ({
              value,
              label,
            }))}
          />
          <p className="help">
            Original codes, brand names and source quotations are preserved.
            Menus and buttons stay in English.
          </p>
        </Section>
        <Section
          title="Search languages"
          description="Choose at least one language for finding identifiers and sale listings."
          className="mt-6"
        >
          <fieldset>
            <legend className="sr-only">Search languages</legend>
            <div className="language-grid">
              {Object.entries(d.languages).map(([code, label]) => (
                <CheckField
                  key={code}
                  name="search_languages"
                  value={code}
                  label={label}
                  defaultChecked={d.preferences.search_languages.includes(code)}
                />
              ))}
            </div>
          </fieldset>
          <p className="help mt-5">
            Languages expand discovery. They do not restrict seller countries or
            delivery locations.
          </p>
        </Section>
        <div className="form-actions">
          <Button type="submit">
            <Save size={16} />
            Save preferences
          </Button>
        </div>
        <p className="help">
          Applies to this installation. Existing results and queued searches
          keep their original settings.
        </p>
      </PostForm>
    </>
  );
}
interface Connection {
  has_key: boolean;
  base_url: string;
  status: string;
  message: string;
  checked_at?: string;
  models: string[];
}
export function Connections() {
  const { data: d } = usePage<{
    connections: Record<string, Connection>;
    error?: string;
    submitted_url?: string;
  }>();
  return (
    <>
      <Heading
        title="AI connections"
        description="Manage the providers used for part research."
      />
      {d.error && <Notice error>{d.error}</Notice>}
      <div className="connection-grid">
        {["codex", "openwebui"].map((provider) => {
          const c = d.connections[provider];
          if (!c) return null;
          return (
            <Section key={provider} className="connection-card">
              <div className="connection-heading">
                <div className="connection-symbol">
                  {provider === "codex" ? (
                    <Terminal size={24} />
                  ) : (
                    <Sparkles size={24} />
                  )}
                </div>
                <div>
                  <h2>{provider === "codex" ? "Codex CLI" : "Open WebUI"}</h2>
                  <p>
                    {provider === "codex"
                      ? "Local research connection"
                      : "Your models, your server"}
                  </p>
                </div>
                <Status status={c.status} />
              </div>
              {provider === "codex" ? (
                <div className="connection-body">
                  <p>
                    Connect your Codex account to research parts, inspect
                    references and explore sources.
                  </p>
                  <div className="code-instruction">
                    <span>Authenticate in your terminal</span>
                    <code>make codex-login</code>
                  </div>
                  <p className="help">
                    The application container uses its own login session. Check
                    the connection after signing in.
                  </p>
                </div>
              ) : (
                <PostForm action="/ai/openwebui">
                  <Field
                    name="base_url"
                    label="Server URL"
                    type="url"
                    required
                    maxLength={2048}
                    defaultValue={d.submitted_url ?? c.base_url}
                    placeholder="http://localhost:3000"
                  />
                  <Field
                    name="api_key"
                    label="API key"
                    type="password"
                    autoComplete="new-password"
                    maxLength={4096}
                    required={!c.has_key}
                    placeholder={
                      c.has_key
                        ? "Leave blank to keep the saved key"
                        : "Enter your API key"
                    }
                    help="Find it in Open WebUI → Settings → Account. When changing servers, enter the key again."
                  />
                  <Button variant="outline" type="submit">
                    Save connection
                  </Button>
                </PostForm>
              )}
              <div className="connection-check">
                <PostForm action={`/ai/${provider}/test`}>
                  <Button type="submit">
                    <RefreshCw size={15} />
                    {provider === "codex"
                      ? "Check authentication & models"
                      : "Test saved connection"}
                  </Button>
                </PostForm>
                <p className="help">
                  Connection checks do not generate responses.
                </p>
                {c.message && (
                  <p
                    className={c.status === "error" ? "error-text" : "help"}
                    role="status"
                  >
                    {c.message}
                  </p>
                )}
                {c.checked_at && (
                  <p className="help">
                    Last checked {date(c.checked_at, true)} UTC
                  </p>
                )}
              </div>
              <details>
                <summary>
                  Available models{" "}
                  <Badge variant="secondary">{c.models.length}</Badge>
                </summary>
                <ul className="model-list">
                  {c.models.length ? (
                    c.models.map((m) => <li key={m}>{m}</li>)
                  ) : (
                    <li>No models listed. Check the connection to refresh.</li>
                  )}
                </ul>
              </details>
            </Section>
          );
        })}
      </div>
      <p className="help mt-6">
        Photo searches need a vision model with tool calling. Enable web search
        in Open WebUI.
      </p>
    </>
  );
}
interface DiscordConfig {
  online: boolean;
  enabled: boolean;
  has_token: boolean;
  channel_id: string;
  owner_id: string;
  app_url: string;
  status: string;
  message?: string;
}
interface Delivery {
  search_id: string;
  vehicle: string;
  created_at: string;
  messages: unknown[];
  last_error?: string;
  status: string;
}
export function Discord() {
  const { data: d } = usePage<{
    config: DiscordConfig;
    submitted: Partial<DiscordConfig>;
    error?: string;
    deliveries: Delivery[];
  }>();
  const c = d.config;
  return (
    <>
      <Heading
        title="Discord"
        description="Bring new part discoveries to your channel."
      />
      {d.error && <Notice error>{d.error}</Notice>}
      <div className="form-layout">
        <div>
          <Section
            title="Bot connection"
            action={
              <Status
                status={
                  c.online ? "ok" : c.status === "error" ? "error" : "untested"
                }
                label={
                  c.online
                    ? "Online"
                    : !c.has_token
                      ? "Not configured"
                      : !c.enabled
                        ? "Disabled"
                        : "Offline"
                }
              />
            }
          >
            <PostForm>
              <Field
                label="Bot token"
                name="bot_token"
                type="password"
                autoComplete="new-password"
                maxLength={256}
                required={!c.has_token}
                placeholder={
                  c.has_token
                    ? "Leave blank to keep the saved token"
                    : "Token from the Discord Developer Portal"
                }
                help="Stored encrypted. Use a bot token, never a personal account token."
              />
              <div className="field-grid">
                <Field
                  name="channel_id"
                  label="Channel ID"
                  required
                  inputMode="numeric"
                  pattern="[0-9]{17,20}"
                  maxLength={20}
                  defaultValue={d.submitted.channel_id ?? c.channel_id}
                />
                <Field
                  name="owner_id"
                  label="Your Discord user ID"
                  required
                  inputMode="numeric"
                  pattern="[0-9]{17,20}"
                  maxLength={20}
                  defaultValue={d.submitted.owner_id ?? c.owner_id}
                />
              </div>
              <Field
                name="app_url"
                label="Application URL (optional)"
                type="url"
                maxLength={2048}
                defaultValue={d.submitted.app_url ?? c.app_url}
                placeholder="http://your-computer:8000"
                help="Use an address your phone can access to link back to requests."
              />
              <CheckField
                name="enabled"
                label="Enable Discord bot"
                defaultChecked={c.enabled || !c.has_token}
              />
              <Button type="submit" className="mt-5">
                Save settings
              </Button>
            </PostForm>
            <div className="connection-check">
              <PostForm action="/discord/test">
                <Button variant="outline" type="submit" disabled={!c.has_token}>
                  Test connection
                </Button>
              </PostForm>
              <p className="help">
                Checks token and channel access. Does not send a message.
              </p>
              {c.message && (
                <p
                  className={c.status === "error" ? "error-text" : "help"}
                  role="status"
                >
                  {c.message}
                </p>
              )}
            </div>
          </Section>
          <Section className="mt-6">
            <details open={!c.has_token}>
              <summary>Set up your bot</summary>
              <ol className="steps">
                <li>
                  Create an application in the{" "}
                  <a
                    href="https://discord.com/developers/applications"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Discord Developer Portal
                  </a>
                  . Generate a token under Bot.
                </li>
                <li>
                  Under Installation → Guild Install, select bot and
                  applications.commands. Grant View Channels, Send Messages,
                  Embed Links and Read Message History. Add the bot to your
                  server.
                </li>
                <li>
                  Enable Developer Mode in Discord’s Advanced settings. Copy
                  your channel ID and user ID into the fields above.
                </li>
                <li>
                  Save the connection, then enable Discord notifications on the
                  weekly schedules you want.
                </li>
              </ol>
            </details>
          </Section>
        </div>
        <aside className="form-aside">
          <MessageSquare size={25} />
          <h2>Only new discoveries</h2>
          <p>
            Scheduled searches send one message for each new piece. Empty or
            failed searches do not generate notifications.
          </p>
          <dl className="command-list">
            <dt>/requests</dt>
            <dd>Latest 10 requests</dd>
            <dt>/schedules</dt>
            <dd>Upcoming schedule slots</dd>
            <dt>/help</dt>
            <dd>Available commands</dd>
          </dl>
          <p>
            Reject asks for confirmation before blacklisting a listing. Restore
            it from the request’s Parts found tab.
          </p>
          <p>Keep the app running to receive alerts.</p>
        </aside>
      </div>
      <Section
        title="Recent deliveries"
        className="mt-8"
        action={
          <a className="text-link" href="/discord">
            Refresh
          </a>
        }
      >
        {d.deliveries.length ? (
          d.deliveries.map((delivery) => (
            <div className="delivery-row" key={delivery.search_id}>
              <div>
                <h3>{delivery.vehicle || "Part request"}</h3>
                <p className="help">
                  {date(delivery.created_at, true)} UTC ·{" "}
                  {delivery.messages.length} pieces sent
                </p>
                {delivery.last_error && (
                  <p className="error-text">{delivery.last_error}</p>
                )}
              </div>
              <Status status={delivery.status} />
              {delivery.status === "failed" && (
                <PostForm
                  action={`/discord/notifications/${delivery.search_id}/retry`}
                >
                  <Button type="submit" variant="outline">
                    Retry
                  </Button>
                </PostForm>
              )}
            </div>
          ))
        ) : (
          <Empty
            icon={MessageSquare}
            title="No deliveries yet"
            description="New pieces from scheduled searches will appear here when notifications are enabled."
          />
        )}
      </Section>
    </>
  );
}
