import type { IdentityDeclaration } from "./types";

const fields: [keyof IdentityDeclaration, string][] = [
  ["underlying_provider", "Underlying provider"], ["underlying_model", "Underlying model"],
  ["model_family", "Model family"], ["model_version", "Exact version"],
  ["access_route", "Inference access route"], ["broker", "Broker / routing"],
  ["harness", "Agent framework / harness"], ["harness_version", "Harness version"],
  ["effort_raw", "Raw provider effort / budget"],
];

export function IdentityEditor({ label, value, onChange }: { label: string; value: IdentityDeclaration; onChange: (value: IdentityDeclaration) => void }) {
  return <details className="identity-editor"><summary>{label} · optional identity declarations</summary>
    <p>Leave unknown values blank. Declarations are not verified model catalogs or private subscription settings. They do not change the actual model or effort controls.</p>
    <div className="lab-grid">{fields.map(([field, title]) => <label key={field}>{title}<input aria-label={`${label} ${title}`} maxLength={field === "effort_raw" ? 512 : 120} value={String(value[field] ?? "")} onChange={e => onChange({ ...value, [field]: e.target.value || undefined })} /></label>)}</div>
    <label className="lab-check"><input type="checkbox" aria-label={`${label} Opt in to alias listing`} checked={value.listing_opt_in ?? false} onChange={e => onChange({ ...value, listing_opt_in: e.target.checked, listing_alias: e.target.checked ? value.listing_alias : undefined })} />Opt in to a bot/player alias in local comparisons</label>
    {value.listing_opt_in && <label>Optional listing alias<input aria-label={`${label} Listing alias`} maxLength={120} value={value.listing_alias ?? ""} onChange={e => onChange({ ...value, listing_alias: e.target.value || undefined })} /></label>}
    <small>No personal information required. Default display names and owners are absent from leaderboards. Hosted publication requires separate access/consent policies.</small>
  </details>;
}
