// The DevLens mark, the same drawing as app/icon.svg: two contour rings around a summit, drawn in
// theme colors so it follows light and dark.
export function LogoMark() {
  return (
    <svg className="logo-mark" viewBox="0 0 32 32" width="28" height="28" aria-hidden="true">
      <path
        className="ring"
        d="M16 3.5 C24 3 29 9 28.5 16.5 C28 24 22.5 28.8 15.5 28.5 C8 28.2 3.4 22.5 3.8 15.6 C4.2 8.6 9 4 16 3.5 Z"
      />
      <path
        className="ring"
        d="M16.2 9 C21 8.8 23.6 12.2 23.3 16.4 C23 20.8 19.8 23.4 15.7 23.2 C11.4 23 8.8 19.8 9 15.7 C9.2 11.6 12 9.2 16.2 9 Z"
      />
      <circle className="summit" cx="16" cy="16" r="3.4" />
    </svg>
  );
}
