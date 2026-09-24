import { TokenProvider, useTokens, calcNestedRadius } from '../shared/tokens';

function OperateModeSurface() {
  const tokens = useTokens();

  const outerRadius = 12;
  const paddingVal = 16;
  const innerRadius = calcNestedRadius(outerRadius, paddingVal);

  return (
    <main
      role="main"
      style={{
        minHeight: '100vh',
        backgroundColor: tokens.colors.surface,
        color: tokens.colors.textPrimary,
        fontFamily: tokens.typography.fontFamily,
        padding: tokens.spacing.xl,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <header
        style={{
          marginBottom: tokens.spacing.semantic.formToSubmit,
          textAlign: 'center',
        }}
      >
        <h1
          style={{
            fontSize: tokens.typography.fontSizes['3xl'],
            fontWeight: tokens.typography.fontWeights.bold,
            lineHeight: tokens.typography.lineHeights.tight,
            margin: 0,
            color: tokens.colors.textPrimary,
          }}
        >
          OpenLibraryOS — Operate Mode
        </h1>
        <p
          style={{
            marginTop: tokens.spacing.sm,
            fontSize: tokens.typography.fontSizes.lg,
            color: tokens.colors.textSecondary,
          }}
        >
          Low-Cognitive-Overhead Library Operations
        </p>
      </header>

      <div
        style={{
          backgroundColor: tokens.colors.surfaceAlt,
          border: `1px solid ${tokens.colors.border}`,
          borderRadius: `${outerRadius}px`,
          padding: `${paddingVal}px`,
          maxWidth: '560px',
          width: '100%',
        }}
      >
        <div
          style={{
            backgroundColor: tokens.colors.surfaceElevated,
            borderRadius: `${innerRadius}px`,
            padding: tokens.spacing.lg,
            border: `1px solid ${tokens.colors.borderMuted}`,
          }}
        >
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: tokens.spacing.sm,
              marginBottom: tokens.spacing.semantic.labelToInput,
            }}
          >
            <span
              role="img"
              aria-label={tokens.colors.status.success.label}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: '20px',
                height: '20px',
                borderRadius: tokens.radius.full,
                backgroundColor: tokens.colors.status.success.bg,
                color: tokens.colors.status.success.color,
                fontWeight: tokens.typography.fontWeights.bold,
                fontSize: tokens.typography.fontSizes.xs,
                border: `1px solid ${tokens.colors.status.success.border}`,
              }}
            >
              ✓
            </span>
            <span
              style={{
                fontWeight: tokens.typography.fontWeights.semibold,
                fontSize: tokens.typography.fontSizes.md,
                color: tokens.colors.textPrimary,
              }}
            >
              Operational Status: Ready
            </span>
          </div>

          <p
            style={{
              margin: 0,
              fontSize: tokens.typography.fontSizes.sm,
              color: tokens.colors.textSecondary,
              lineHeight: tokens.typography.lineHeights.normal,
            }}
          >
            Offline foundation verified. Foundational design tokens, anti-glare surfaces,
            and keyboard focus indicators initialized for high-throughput circulation and catalog workflows.
          </p>
        </div>
      </div>
    </main>
  );
}

export function App() {
  return (
    <TokenProvider>
      <OperateModeSurface />
    </TokenProvider>
  );
}

export default App;
