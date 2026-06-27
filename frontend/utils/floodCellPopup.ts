type FloodCellExplainResult = {
  in_flood?: boolean;
  reason?: string | null;
  elevation_m?: number | null;
  distance_from_dam_m?: number | null;
  location?: {
    county?: string | null;
    town?: string | null;
    village?: string | null;
  } | null;
};

function escapeHtml(value: unknown): string {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatLocation(result: FloodCellExplainResult): string {
  const locationLabel = result.location
    ? [result.location.county, result.location.town, result.location.village]
        .filter(Boolean)
        .join(" ")
    : "未命中村里界";
  return escapeHtml(locationLabel);
}

function formatDistanceKm(distanceM: number | null | undefined): string {
  return distanceM != null ? `${(distanceM / 1000).toFixed(1)}km` : "-";
}

function formatElevation(elevationM: number | null | undefined): string {
  return elevationM != null ? `${elevationM}m` : "-";
}

export function buildFloodCellPopupHtml(result: FloodCellExplainResult): string {
  const isFlooded = !!result.in_flood;
  const statusLabel = isFlooded ? "淹水區" : "非淹水區";
  const badge = isFlooded ? "color:#3d7d9a;font-weight:600" : "color:#999";
  const reason = escapeHtml(result.reason ?? "無說明資料。");
  const locationLabel = formatLocation(result);
  const elevation = escapeHtml(formatElevation(result.elevation_m));
  const distance = escapeHtml(formatDistanceKm(result.distance_from_dam_m));

  return `<div style="font-size:12.5px;line-height:1.7">
    <b style="${badge}">${statusLabel}</b><br>
    ${reason}<br>
    <span style="color:#999;font-size:11px">
      高程 ${elevation} · 距壩 ${distance} · ${locationLabel}
    </span>
  </div>`;
}
