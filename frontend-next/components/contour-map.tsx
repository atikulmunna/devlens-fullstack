// The home page's illustration: a changed file at the summit, the files that import it on the
// contour lines around it. It is how DevLens draws a commit's blast radius, drawn as terrain.
export function ContourMap() {
  return (
    <svg
      className="contours"
      viewBox="0 0 400 350"
      role="img"
      aria-label="A changed file at the center, with the files that import it on contour lines around it"
    >
      <path
        className="ring-faint"
        d="M218 20 C304 14 362 78 358 152 C356 190 376 226 352 262 C326 302 276 318 236 322 C196 326 168 344 124 334 C76 323 50 284 54 236 C56 204 36 172 50 132 C68 74 134 26 218 20 Z"
      />
      <path
        className="ring"
        d="M214 56 C280 50 326 96 324 150 C322 180 336 206 320 236 C302 270 262 278 230 282 C200 286 180 306 144 300 C104 294 82 262 86 222 C88 196 72 170 84 140 C98 98 150 60 214 56 Z"
      />
      <path
        className="ring"
        d="M210 92 C258 88 284 122 282 160 C280 200 262 232 226 238 C196 243 178 262 150 258 C120 254 108 226 116 196 C122 172 128 150 140 128 C154 104 178 94 210 92 Z"
      />
      <path
        className="ring"
        d="M205 128 C232 126 246 146 244 166 C242 188 226 202 204 200 C182 198 166 186 166 166 C166 144 180 130 205 128 Z"
      />

      <circle className="node-changed" cx="205" cy="164" r="8" />
      <text className="label" x="205" y="188" textAnchor="middle">
        auth/jwt.py
      </text>

      <circle className="node" cx="244" cy="166" r="5" />
      <text className="label" x="252" y="162">
        session.py
      </text>
      <circle className="node" cx="116" cy="196" r="5" />
      <text className="label" x="108" y="200" textAnchor="end">
        chat.py
      </text>
      <circle className="node" cx="320" cy="236" r="5" />
      <text className="label" x="328" y="240">
        deps.py
      </text>
      <circle className="node" cx="144" cy="300" r="5" />
      <text className="label" x="152" y="304">
        main.py
      </text>
    </svg>
  );
}
