/**
 * Human-readable labels for screen universe ids (PRD-23c).
 *
 * The backend persists a screen's universe as an id string — `"sp500"` or
 * `"sector_<key>"` (only standing universes are trackable; see
 * ScreenSaveRequest._standing_only). This renders them for the My Screens
 * surfaces.
 */

/** `"sp500"` → "S&P 500"; `"sector_technology"` → "Technology sector". */
export function universeLabel(universeId: string): string {
  if (universeId === "sp500") return "S&P 500";
  if (universeId.startsWith("sector_")) {
    const key = universeId.slice("sector_".length).replace(/[_-]+/g, " ");
    const titled = key
      .split(" ")
      .filter(Boolean)
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
      .join(" ");
    return titled ? `${titled} sector` : "Sector";
  }
  return universeId;
}
