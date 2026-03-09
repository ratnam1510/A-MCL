"use client";

import { useState } from "react";

const E = "cubic-bezier(0.4,0,0.2,1)";
const ACCENT = "#C4654A";
const TX = "#E8E0D0";
const TX2 = "#A69E90";
const TX3 = "#6D655A";
const TX4 = "#3A3530";
const TX5 = "#252220";

/* ─── Command Row ───────────────────────────────────────────────────────── */

function CmdRow({
  label,
  command,
  copied,
  onCopy,
  delay = "0s",
}: {
  label: string;
  command: string;
  copied: boolean;
  onCopy: () => void;
  delay?: string;
}) {
  const [h, setH] = useState(false);
  const [p, setP] = useState(false);

  return (
    <div
      role="button"
      tabIndex={0}
      aria-label={`Copy: ${command}`}
      onClick={onCopy}
      onKeyDown={(e) => e.key === "Enter" && onCopy()}
      onMouseEnter={() => setH(true)}
      onMouseLeave={() => { setH(false); setP(false); }}
      onMouseDown={() => setP(true)}
      onMouseUp={() => setP(false)}
      style={{
        display: "flex",
        alignItems: "center",
        gap: "20px",
        padding: "18px 24px",
        borderLeft: `2px solid ${h ? ACCENT : TX4}`,
        background: h ? "#161210" : "transparent",
        cursor: "pointer",
        userSelect: "none",
        outline: "none",
        transition: `all 0.2s ${E}`,
        transform: p ? "scale(0.995)" : h ? "translateX(6px)" : "none",
        animation: `fadeUp 0.7s ${E} ${delay} both`,
      }}
    >
      <div style={{ flex: 1, minWidth: 0 }}>
        <p
          style={{
            fontSize: "9px",
            textTransform: "uppercase",
            letterSpacing: "0.24em",
            color: TX4,
            fontWeight: 500,
            marginBottom: "8px",
          }}
        >
          {label}
        </p>
        <code
          style={{
            fontSize: "15px",
            color: TX,
            letterSpacing: "-0.01em",
          }}
        >
          <span style={{ color: TX3 }}>$ </span>
          {command}
        </code>
      </div>

      <span
        style={{
          fontSize: "10px",
          fontWeight: 500,
          color: copied ? ACCENT : h ? TX2 : TX4,
          letterSpacing: "0.08em",
          textTransform: "uppercase",
          transition: `color 0.2s ${E}`,
          flexShrink: 0,
          minWidth: "36px",
          textAlign: "right",
        }}
      >
        {copied ? "done" : "copy"}
      </span>
    </div>
  );
}

/* ─── Feature Entry ─────────────────────────────────────────────────────── */

function Feature({
  num,
  title,
  desc,
  delay = "0s",
}: {
  num: string;
  title: string;
  desc: string;
  delay?: string;
}) {
  const [h, setH] = useState(false);

  return (
    <div
      onMouseEnter={() => setH(true)}
      onMouseLeave={() => setH(false)}
      style={{
        display: "grid",
        gridTemplateColumns: "52px 1fr",
        gap: "0",
        padding: "24px 0",
        borderTop: `1px solid ${h ? "rgba(232,224,208,0.09)" : "rgba(232,224,208,0.04)"}`,
        transition: `border-color 0.2s ${E}`,
        animation: `fadeUp 0.65s ${E} ${delay} both`,
      }}
    >
      <span
        style={{
          fontFamily: "'Fraunces', Georgia, serif",
          fontSize: "18px",
          fontWeight: 300,
          fontStyle: "italic",
          color: h ? ACCENT : TX4,
          transition: `color 0.2s ${E}`,
          paddingTop: "2px",
        }}
      >
        {num}
      </span>
      <div>
        <p
          style={{
            fontFamily: "'Fraunces', Georgia, serif",
            fontSize: "18px",
            fontWeight: 600,
            color: h ? TX : TX2,
            letterSpacing: "-0.02em",
            marginBottom: "6px",
            transition: `color 0.2s ${E}`,
          }}
        >
          {title}
        </p>
        <p
          style={{
            fontSize: "13px",
            color: TX3,
            lineHeight: 1.65,
          }}
        >
          {desc}
        </p>
      </div>
    </div>
  );
}

/* ─── Page ───────────────────────────────────────────────────────────────── */

export default function Home() {
  const [copiedCli, setCopiedCli] = useState(false);
  const [copiedPip, setCopiedPip] = useState(false);

  const copy = (text: string, setter: (v: boolean) => void) => {
    navigator.clipboard.writeText(text);
    setter(true);
    setTimeout(() => setter(false), 2400);
  };

  return (
    <main
      style={{
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
        position: "relative",
      }}
    >
      {/* ── Asymmetric corner glow ── */}
      <div
        aria-hidden
        style={{
          position: "fixed",
          top: "-20%",
          left: "-12%",
          width: "70%",
          height: "60%",
          background:
            "radial-gradient(ellipse at center, rgba(196,101,74,0.07) 0%, transparent 55%)",
          filter: "blur(90px)",
          pointerEvents: "none",
          mixBlendMode: "screen",
        }}
      />

      {/* ── Full-width nav ── */}
      <nav
        style={{
          width: "100%",
          padding: "36px clamp(32px, 5vw, 80px)",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          position: "relative",
          zIndex: 2,
          animation: `fadeUp 0.5s ${E} both`,
        }}
      >
        <span
          style={{
            fontFamily: "'Fraunces', Georgia, serif",
            fontWeight: 700,
            fontSize: "20px",
            fontStyle: "italic",
            color: TX,
            letterSpacing: "-0.04em",
          }}
        >
          a:mcl
        </span>

        <a
          href="https://pypi.org/project/amcl-server/"
          target="_blank"
          rel="noreferrer"
          style={{
            fontSize: "12px",
            fontWeight: 500,
            color: TX4,
            textDecoration: "none",
            letterSpacing: "0.06em",
            transition: `color 0.2s ${E}`,
          }}
          onMouseEnter={(e) => {
            (e.currentTarget as HTMLAnchorElement).style.color = TX2;
          }}
          onMouseLeave={(e) => {
            (e.currentTarget as HTMLAnchorElement).style.color = TX4;
          }}
        >
          PyPI
        </a>
      </nav>

      {/* ── Hero — full viewport width ── */}
      <section
        style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          padding: "clamp(40px, 8vh, 100px) clamp(32px, 5vw, 80px)",
          position: "relative",
          zIndex: 1,
        }}
      >
        {/* ── THE HEADLINE — fills the viewport ── */}
        <h1
          style={{
            fontFamily: "'Fraunces', Georgia, serif",
            fontWeight: 900,
            fontSize: "clamp(4.5rem, 12vw, 12rem)",
            letterSpacing: "-0.04em",
            lineHeight: 0.88,
            marginBottom: "clamp(36px, 5vh, 64px)",
            animation: `fadeUp 0.8s ${E} 0.06s both`,
            maxWidth: "1200px",
          }}
        >
          <span style={{ display: "block", color: TX }}>Shared</span>
          <span
            style={{
              display: "block",
              color: ACCENT,
              fontStyle: "italic",
            }}
          >
            context—
          </span>
          <span
            style={{
              display: "block",
              color: "rgba(232,224,208,0.12)",
              fontStyle: "italic",
            }}
          >
            every agent.
          </span>
        </h1>

        {/* ── Two-column: tagline left, commands right ── */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: "clamp(32px, 4vw, 80px)",
            maxWidth: "1100px",
            alignItems: "start",
          }}
        >
          {/* Tagline */}
          <p
            style={{
              fontSize: "15px",
              fontWeight: 400,
              color: TX3,
              lineHeight: 1.85,
              maxWidth: "480px",
              animation: `fadeUp 0.7s ${E} 0.12s both`,
            }}
          >
            One persistent memory layer across Cursor, Claude, Amp.
            Every decision, conversation, and file change — always in sync.
          </p>

          {/* Commands */}
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "2px",
            }}
          >
            <CmdRow
              label="Install"
              command="pip install amcl-server"
              copied={copiedPip}
              onCopy={() => copy("pip install amcl-server", setCopiedPip)}
              delay="0.18s"
            />
            <CmdRow
              label="Share"
              command="amcl share --url"
              copied={copiedCli}
              onCopy={() => copy("amcl share --url", setCopiedCli)}
              delay="0.22s"
            />
          </div>
        </div>
      </section>

      {/* ── Features — full-width 4-column ── */}
      <section
        style={{
          padding: "clamp(48px, 6vh, 80px) clamp(32px, 5vw, 80px)",
          position: "relative",
          zIndex: 1,
        }}
      >
        <p
          style={{
            fontSize: "9px",
            textTransform: "uppercase",
            letterSpacing: "0.24em",
            color: TX4,
            fontWeight: 500,
            marginBottom: "12px",
            animation: `fadeUp 0.65s ${E} 0.3s both`,
          }}
        >
          Why amcl
        </p>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(4, 1fr)",
            gap: "0",
            borderTop: "1px solid rgba(232,224,208,0.04)",
            borderBottom: "1px solid rgba(232,224,208,0.04)",
            maxWidth: "1100px",
          }}
        >
          {[
            { num: "01", title: "Universal", desc: "Cursor, Claude Code, Amp, Windsurf, Copilot — one shared layer.", delay: "0.33s" },
            { num: "02", title: "Shareable", desc: "One URL for any conversation. Drop it in Slack, open it anywhere.", delay: "0.36s" },
            { num: "03", title: "Persistent", desc: "Context survives every agent switch. Zero information loss.", delay: "0.39s" },
            { num: "04", title: "Retroactive", desc: "Import history from agents you used before installing.", delay: "0.42s" },
          ].map(({ num, title, desc, delay }) => (
            <FeatureCol key={num} num={num} title={title} desc={desc} delay={delay} />
          ))}
        </div>
      </section>

      {/* ── Footer ── */}
      <footer
        style={{
          padding: "32px clamp(32px, 5vw, 80px) 48px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          flexWrap: "wrap",
          gap: "12px",
          borderTop: "1px solid rgba(232,224,208,0.04)",
          position: "relative",
          zIndex: 1,
          animation: `fadeUp 0.65s ${E} 0.48s both`,
        }}
      >
        <span
          style={{
            fontFamily: "'Fraunces', Georgia, serif",
            fontSize: "16px",
            fontWeight: 600,
            fontStyle: "italic",
            color: TX5,
            letterSpacing: "-0.03em",
          }}
        >
          a:mcl
        </span>
        <span
          style={{
            fontSize: "11px",
            color: TX5,
            letterSpacing: "0.06em",
          }}
        >
          amcl-server v1.1.0 · jpdz.app
        </span>
      </footer>
    </main>
  );
}

/* ─── Feature Column (for 4-col grid) ───────────────────────────────────── */

function FeatureCol({
  num,
  title,
  desc,
  delay = "0s",
}: {
  num: string;
  title: string;
  desc: string;
  delay?: string;
}) {
  const [h, setH] = useState(false);

  return (
    <div
      onMouseEnter={() => setH(true)}
      onMouseLeave={() => setH(false)}
      style={{
        padding: "28px 28px 28px 0",
        borderRight: "1px solid rgba(232,224,208,0.04)",
        transition: `background 0.2s ${E}`,
        animation: `fadeUp 0.65s ${E} ${delay} both`,
      }}
    >
      <span
        style={{
          fontFamily: "'Fraunces', Georgia, serif",
          fontSize: "15px",
          fontWeight: 300,
          fontStyle: "italic",
          color: h ? ACCENT : TX4,
          transition: `color 0.2s ${E}`,
          display: "block",
          marginBottom: "16px",
        }}
      >
        {num}
      </span>
      <p
        style={{
          fontFamily: "'Fraunces', Georgia, serif",
          fontSize: "17px",
          fontWeight: 600,
          color: h ? TX : TX2,
          letterSpacing: "-0.02em",
          marginBottom: "8px",
          transition: `color 0.2s ${E}`,
        }}
      >
        {title}
      </p>
      <p
        style={{
          fontSize: "12px",
          color: TX3,
          lineHeight: 1.65,
        }}
      >
        {desc}
      </p>
    </div>
  );
}
