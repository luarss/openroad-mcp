// Process exit codes for the CLI entrypoint. 130 follows the shell convention
// for a process terminated by SIGINT (128 + 2).
export const EXIT_CODE_ERROR = 1;
export const EXIT_CODE_KEYBOARD_INTERRUPT = 130;

export const MAX_COMMAND_COMPLETION_WINDOW = 0.1;

export const PROCESS_SHUTDOWN_TIMEOUT = 2.0;
export const FORCE_EXIT_DELAY_SECONDS = 2;

export const RECENT_OUTPUT_LINES = 20;
export const LAST_COMMANDS_COUNT = 5;

export const BYTES_TO_MB = 1024 * 1024;

export const UTILIZATION_PERCENTAGE_BASE = 100;
export const LARGE_BUFFER_THRESHOLD = 10 * 1024 * 1024;
export const SIGNIFICANT_LOG_THRESHOLD = 100_000;

export const CHUNK_JOIN_THRESHOLD = 100;

/**
 * Per-session retention of recent command output, so it can be searched after
 * the fact.
 *
 * The circular buffer cannot serve this: runCommand drains it to empty, so a
 * search over the live buffer finds nothing. Retention is capped by total
 * characters and by number of commands, oldest evicted first.
 */
export const OUTPUT_HISTORY_DEFAULTS = {
  MAX_CHARS: 256 * 1024,
  MAX_COMMANDS: 50,
} as const;

/**
 * Flow-run defaults.
 *
 * A route on a real design runs for hours, so the default timeout is measured
 * in hours rather than the seconds a Tcl command gets. MAX_JOBS is deliberately
 * small: a flow run is far heavier than an interactive session, and nothing
 * else on the server governs resource use.
 */
export const FLOW_RUN_DEFAULTS = {
  TIMEOUT_SECONDS: 6 * 60 * 60,
  MAX_JOBS: 2,
  /** Grace period between SIGTERM and SIGKILL when tearing a run down. */
  KILL_GRACE_MS: 5000,
} as const;

/**
 * The QoR dashboard (palantir) that `read_orfs_metrics` asks when `check_qor` is
 * set. ORFS `make metadata-check` talks to the same service.
 */
export const DEFAULT_QOR_API_URL = "https://dashboard.precisioninno.com/api";

/**
 * Platforms that `check_qor` may send to the QoR dashboard: the platform
 * directories of the public ORFS repository (`flow/platforms`, without `common`).
 * Any other platform may carry private PDK data, so its metrics stay local.
 * Add a platform here when ORFS adds a public one.
 */
export const PUBLIC_QOR_PLATFORMS: readonly string[] = [
  "asap7",
  "gf180",
  "gt2n",
  "ihp-sg13g2",
  "nangate45",
  "sky130hd",
  "sky130hs",
  "sky130io",
  "sky130ram",
];

/**
 * Report-image budget defaults.
 *
 * MAX_BASE64_KB is the payload ceiling in KB of base64. The previous 15 KB
 * ceiling forced every render down to the resize floor -- a 1099x1099 image
 * became 256x256 -- which is unreadable for the congestion and IR-drop
 * heatmaps these tools exist to show.
 *
 * MAX_DIMENSION is the longest edge worth sending: vision models downsample
 * beyond roughly this, so extra pixels cost payload without adding detail.
 */
export const IMAGE_DEFAULTS = {
  MAX_BASE64_KB: 1024,
  MAX_DIMENSION: 1568,
  MIN_DIMENSION: 512,
} as const;

/**
 * Banner prepended to any command output that lost characters to buffer
 * overflow.
 *
 * The structured `truncated` / `bytes_discarded` fields carry the same fact,
 * but a consumer reads `output` first: a result that silently begins mid-line
 * reads as a complete answer, and has been acted on as one. Putting the notice
 * in the text itself makes that mistake impossible.
 */
export function truncationNotice(
  discarded: number,
  total: number,
  retained: number,
): string {
  const n = (v: number): string => v.toLocaleString("en-US");
  return (
    `[TRUNCATED: ${n(discarded)} of ${n(total)} characters were discarded from the START of this output.\n` +
    ` What follows is the LAST ${n(retained)} characters only, and may begin mid-line. Any error or\n` +
    ` warning printed before this point is NOT visible here. Narrow the query and re-run.]\n` +
    `---\n`
  );
}

export const LARGE_IO_THRESHOLD = 10_000;
export const SLOW_OPERATION_THRESHOLD = 1.0;

// Bounds memory on long-lived sessions; oldest entries are dropped when
// exceeded.
export const MAX_COMMAND_HISTORY = 1000;

/**
 * PTY geometry and terminal type.
 *
 * OpenROAD runs a readline-style line editor when stdin is a TTY. At a narrow
 * width that editor horizontally scrolls long commands, redrawing the whole
 * visible window once per character -- a single 75-character read_liberty turns
 * into a cascade of near-identical lines that swamps the real output. A width
 * far beyond any realistic command avoids the redraw entirely.
 *
 * TERM=dumb tells readline to skip the fancy editing layer (bracketed paste,
 * horizontal scroll, cursor addressing) that we neither need nor can interpret.
 */
export const PTY_COLS = 4096;
export const PTY_ROWS = 24;
export const PTY_TERM = "dumb";

/**
 * Line terminator written after each command. A real Enter key sends carriage
 * return, and a line editor in raw mode binds CR -- not LF -- to accept-line.
 * Sending LF can leave the command sitting unsubmitted in the edit buffer.
 */
export const PTY_LINE_TERMINATOR = "\r";

/**
 * Budget for the startup handshake. This has to cover the whole cold start --
 * loading OpenROAD and reaching its prompt -- not just the probe round-trip,
 * because spawning does not wait for readiness. OpenROAD is native C++ and a
 * healthy start is sub-second locally, so this is a few seconds of margin for
 * a slow disk/container, not an expected duration: the handshake exists to
 * catch a session that will never respond, not to tolerate a slow one.
 */
export const SESSION_HANDSHAKE_TIMEOUT_MS = 10_000;
