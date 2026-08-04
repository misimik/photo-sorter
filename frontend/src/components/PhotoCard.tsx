import { forwardRef } from "react";
import type { Photo } from "../api";
import { thumbnailUrl } from "../api";

interface Props {
  photo: Photo;
  isFocused: boolean;
  onRate: (stars: number) => void;
  onToggle: (toggle: "reject" | "favorite" | "blurry" | "unreject" | "unfavorite" | "unblurry") => void;
  onZoom: () => void;
  onFocus: () => void;
}

const PhotoCard = forwardRef<HTMLDivElement, Props>(
  function PhotoCard({ photo, isFocused, onRate, onToggle, onZoom, onFocus }, ref) {
    const blurIndicator = !photo.user_blurry_override && photo.is_blurry === 1;

    return (
      <div
        ref={ref}
        tabIndex={0}
        onFocus={onFocus}
        onClick={onFocus}
        style={{
          background: "#1a1a1a",
          border: isFocused
            ? "2px solid #5af"
            : photo.is_favorite
            ? "2px solid #fa0"
            : photo.is_rejected
            ? "2px solid #f44"
            : "2px solid #333",
          borderRadius: "8px",
          overflow: "hidden",
          opacity: photo.is_rejected ? 0.5 : 1,
          outline: "none",
          transition: "border-color 0.15s",
          display: "flex",
          flexDirection: "column",
          minHeight: 0,
        }}
      >
        <div onClick={onZoom} style={{ cursor: "zoom-in", position: "relative", flex: 1, minHeight: 0 }}>
          <img
            src={thumbnailUrl(photo.id)}
            alt={photo.filename}
            loading="lazy"
            style={{ width: "100%", height: "100%", display: "block", objectFit: "contain", background: "#0a0a0a" }}
          />
          {blurIndicator && (
            <span style={badgeStyle("#f44")}>⚠</span>
          )}
          {photo.stars != null && photo.stars > 0 && (
            <span style={badgeStyle("#fa0")}>{"★".repeat(photo.stars)}</span>
          )}
        </div>

        <div style={{ padding: "5px 6px", display: "flex", gap: 3, flexWrap: "wrap" }}>
          {[1, 2, 3, 4, 5].map((s) => (
            <button
              key={s}
              onClick={(e) => { e.stopPropagation(); onRate(s); }}
              style={starBtnStyle(s <= (photo.stars || 0))}
            >
              {s <= (photo.stars || 0) ? "★" : "☆"}
            </button>
          ))}
          <ToggleBtn
            active={!!photo.is_rejected}
            onClick={() => onToggle(photo.is_rejected ? "unreject" : "reject")}
          >
            ✕
          </ToggleBtn>
          <ToggleBtn
            active={!!photo.is_favorite}
            onClick={() => onToggle(photo.is_favorite ? "unfavorite" : "favorite")}
          >
            ♥
          </ToggleBtn>
        </div>
      </div>
    );
  }
);

function ToggleBtn({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={(e) => { e.stopPropagation(); onClick(); }}
      style={{
        border: "none",
        borderRadius: "3px",
        width: 26,
        height: 22,
        cursor: "pointer",
        fontSize: "12px",
        marginLeft: "auto",
        background: active ? "#f44" : "#333",
        color: active ? "#fff" : "#777",
      }}
    >
      {children}
    </button>
  );
}

const badgeStyle = (bg: string): React.CSSProperties => ({
  position: "absolute",
  top: 6, left: 6,
  background: bg,
  color: "#fff",
  padding: "2px 6px",
  borderRadius: "4px",
  fontSize: "11px",
  fontWeight: 700,
});

const starBtnStyle = (active: boolean): React.CSSProperties => ({
  background: active ? "#fa0" : "#333",
  color: active ? "#000" : "#777",
  border: "none",
  borderRadius: "3px",
  width: 26,
  height: 22,
  cursor: "pointer",
  fontSize: "12px",
});

export default PhotoCard;
