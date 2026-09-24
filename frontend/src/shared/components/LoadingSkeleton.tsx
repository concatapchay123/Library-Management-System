import React from 'react';
import { useTokens } from '../tokens';

export interface LoadingSkeletonProps {
  lines?: number;
  height?: string | number;
  ariaLabel?: string;
  className?: string;
  style?: React.CSSProperties;
}

/**
 * Accessible Skeleton Shimmer Component for OpenLibraryOS.
 *
 * Implements UI/UX Invariant Module 5:
 * "Skeleton Loading thay cho Spinner trung tâm: Với các trang tải dữ liệu nội dung,
 * BẮT BUỘC hiển thị khung xương mờ ảo (Skeleton shimmer) mô phỏng chính xác cấu trúc
 * trang sắp tải. Tránh để trang trống rỗng với một vòng xoay spinner nhỏ ở giữa gây sốt ruột."
 */
export function LoadingSkeleton({
  lines = 3,
  height = '16px',
  ariaLabel = 'Loading content...',
  className,
  style,
}: LoadingSkeletonProps) {
  const tokens = useTokens();

  const shimmerKeyframes = `
    @keyframes skeleton-shimmer {
      0% { opacity: 0.5; background-position: -200% 0; }
      50% { opacity: 0.8; }
      100% { opacity: 0.5; background-position: 200% 0; }
    }
  `;

  return (
    <div
      role="status"
      aria-busy="true"
      aria-label={ariaLabel}
      className={className}
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: tokens.spacing.sm,
        width: '100%',
        padding: tokens.spacing.md,
        boxSizing: 'border-box',
        ...style,
      }}
    >
      <style>{shimmerKeyframes}</style>
      <span className="sr-only" style={{ position: 'absolute', width: 1, height: 1, overflow: 'hidden' }}>
        {ariaLabel}
      </span>

      {Array.from({ length: lines }).map((_, index) => {
        // Vary width for a realistic content shimmer effect
        const width = index === 0 ? '60%' : index === lines - 1 ? '75%' : '100%';
        return (
          <div
            key={index}
            data-testid="skeleton-shimmer-bar"
            aria-hidden="true"
            style={{
              height,
              width,
              borderRadius: tokens.radius.sm,
              backgroundColor: tokens.colors.surfaceAlt,
              backgroundImage: `linear-gradient(90deg, ${tokens.colors.surfaceAlt} 0%, ${tokens.colors.border} 50%, ${tokens.colors.surfaceAlt} 100%)`,
              backgroundSize: '200% 100%',
              animation: 'skeleton-shimmer 1.5s ease-in-out infinite',
            }}
          />
        );
      })}
    </div>
  );
}

export default LoadingSkeleton;
