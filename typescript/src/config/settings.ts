import os from "node:os";
import path from "node:path";
import fs from "node:fs";
import { DEFAULT_QOR_API_URL, FLOW_RUN_DEFAULTS, IMAGE_DEFAULTS, OUTPUT_HISTORY_DEFAULTS } from "../constants.js";

const TRUTHY_VALUES = ["true", "1", "yes"];
const FALSY_VALUES = ["false", "0", "no"];

function parseBool(envKey: string, val: string): boolean {
  const normalized = val.trim().toLowerCase();
  if (TRUTHY_VALUES.includes(normalized)) return true;
  if (FALSY_VALUES.includes(normalized)) return false;
  throw new Error(
    `Invalid value for ${envKey}: ${val}. Expected a boolean ` +
      `(${TRUTHY_VALUES.join("/")} or ${FALSY_VALUES.join("/")}).`,
  );
}

function parseFloat_(envKey: string, val: string, allowZero: boolean): number {
  if (val.trim() === "") throw new Error(`Invalid value for ${envKey}: (empty string). Expected float.`);
  const n = Number(val);
  const bound = allowZero ? "non-negative" : "positive";
  if (!Number.isFinite(n) || n < 0 || (!allowZero && n === 0)) {
    throw new Error(`Invalid value for ${envKey}: ${val}. Expected a ${bound} finite float.`);
  }
  return n;
}

function parseInt_(envKey: string, val: string, allowZero: boolean): number {
  if (val.trim() === "") throw new Error(`Invalid value for ${envKey}: (empty string). Expected int.`);
  if (!/^-?\d+$/.test(val.trim())) throw new Error(`Invalid value for ${envKey}: ${val}. Expected int.`);
  const n = Number(val);
  const bound = allowZero ? "non-negative" : "positive";
  if (n < 0 || (!allowZero && n === 0)) {
    throw new Error(`Invalid value for ${envKey}: ${val}. Expected a ${bound} integer.`);
  }
  return n;
}

export class Settings {
  readonly COMMAND_TIMEOUT: number;
  readonly COMMAND_COMPLETION_DELAY: number;
  readonly DEFAULT_BUFFER_SIZE: number;
  readonly MAX_SESSIONS: number;
  readonly SESSION_QUEUE_SIZE: number;
  readonly SESSION_IDLE_TIMEOUT: number;
  readonly READ_CHUNK_SIZE: number;
  readonly LOG_LEVEL: string;
  readonly LOG_FORMAT: string;
  readonly ALLOWED_COMMANDS: string[];
  readonly ENABLE_COMMAND_VALIDATION: boolean;
  readonly WHITELIST_ENABLED: boolean;
  readonly ORFS_FLOW_PATH: string;
  /** Base URL of the QoR dashboard that `read_orfs_metrics` asks when `check_qor` is set. */
  readonly QOR_API_URL: string;
  /**
   * Budget for a report image, measured in KB of base64.
   *
   * This is the knob that decides whether a congestion or IR-drop heatmap is
   * actually readable. The old 15 KB ceiling forced every image down to the
   * 256x256 floor, which is useless for the heatmaps these tools exist to
   * show.
   */
  readonly IMAGE_MAX_BASE64_KB: number;
  /**
   * Longest edge, in pixels, an image is resized down to before encoding.
   * Defaults to the resolution ceiling vision models downsample to anyway --
   * sending more pixels costs payload without adding detail.
   */
  readonly IMAGE_MAX_DIMENSION: number;
  /** Longest edge below which the resize ladder refuses to shrink further. */
  readonly IMAGE_MIN_DIMENSION: number;
  /** Directory flow-run logs are streamed to. Never the session buffer. */
  readonly RUN_LOG_DIR: string;
  /** Concurrent flow runs allowed. */
  readonly MAX_FLOW_JOBS: number;
  /** Default wall-clock budget for a flow run, in seconds. */
  readonly FLOW_RUN_TIMEOUT: number;
  /** Characters of recent command output retained per session for searching. */
  readonly OUTPUT_HISTORY_CHARS: number;
  /** Commands of output retained per session for searching. */
  readonly OUTPUT_HISTORY_COMMANDS: number;

  constructor(overrides: Partial<Settings> = {}) {
    this.COMMAND_TIMEOUT = overrides.COMMAND_TIMEOUT ?? 30.0;
    this.COMMAND_COMPLETION_DELAY = overrides.COMMAND_COMPLETION_DELAY ?? 0.1;
    this.DEFAULT_BUFFER_SIZE = overrides.DEFAULT_BUFFER_SIZE ?? 128 * 1024;
    this.MAX_SESSIONS = overrides.MAX_SESSIONS ?? 50;
    this.SESSION_QUEUE_SIZE = overrides.SESSION_QUEUE_SIZE ?? 128;
    this.SESSION_IDLE_TIMEOUT = overrides.SESSION_IDLE_TIMEOUT ?? 300.0;
    this.READ_CHUNK_SIZE = overrides.READ_CHUNK_SIZE ?? 8192;
    this.LOG_LEVEL = overrides.LOG_LEVEL ?? "INFO";
    this.LOG_FORMAT = overrides.LOG_FORMAT ?? "%(asctime)s - %(name)s - %(levelname)s - %(message)s";
    this.ALLOWED_COMMANDS = overrides.ALLOWED_COMMANDS ?? ["openroad"];
    this.ENABLE_COMMAND_VALIDATION = overrides.ENABLE_COMMAND_VALIDATION ?? true;
    this.WHITELIST_ENABLED = overrides.WHITELIST_ENABLED ?? true;
    this.ORFS_FLOW_PATH = overrides.ORFS_FLOW_PATH ?? path.join(os.homedir(), "OpenROAD-flow-scripts", "flow");
    this.QOR_API_URL = overrides.QOR_API_URL ?? DEFAULT_QOR_API_URL;
    this.IMAGE_MAX_BASE64_KB = overrides.IMAGE_MAX_BASE64_KB ?? IMAGE_DEFAULTS.MAX_BASE64_KB;
    this.IMAGE_MAX_DIMENSION = overrides.IMAGE_MAX_DIMENSION ?? IMAGE_DEFAULTS.MAX_DIMENSION;
    this.IMAGE_MIN_DIMENSION = overrides.IMAGE_MIN_DIMENSION ?? IMAGE_DEFAULTS.MIN_DIMENSION;
    this.RUN_LOG_DIR = overrides.RUN_LOG_DIR ?? path.join(os.tmpdir(), "openroad-mcp-runs");
    this.MAX_FLOW_JOBS = overrides.MAX_FLOW_JOBS ?? FLOW_RUN_DEFAULTS.MAX_JOBS;
    this.FLOW_RUN_TIMEOUT = overrides.FLOW_RUN_TIMEOUT ?? FLOW_RUN_DEFAULTS.TIMEOUT_SECONDS;
    this.OUTPUT_HISTORY_CHARS = overrides.OUTPUT_HISTORY_CHARS ?? OUTPUT_HISTORY_DEFAULTS.MAX_CHARS;
    this.OUTPUT_HISTORY_COMMANDS =
      overrides.OUTPUT_HISTORY_COMMANDS ?? OUTPUT_HISTORY_DEFAULTS.MAX_COMMANDS;
  }

  get flowPath(): string {
    return path.resolve(this.ORFS_FLOW_PATH.replace(/^~/, os.homedir()));
  }

  get platforms(): string[] {
    const platformsDir = path.join(this.flowPath, "platforms");
    try {
      return fs.readdirSync(platformsDir, { withFileTypes: true })
        .filter((d) => d.isDirectory())
        .map((d) => d.name);
    } catch {
      return [];
    }
  }

  designs(platform: string): string[] {
    const designsDir = path.join(this.flowPath, "designs", platform);
    try {
      return fs.readdirSync(designsDir, { withFileTypes: true })
        .filter((d) => d.isDirectory())
        .map((d) => d.name);
    } catch {
      return [];
    }
  }

  static fromEnv(): Settings {
    const overrides: { -readonly [K in keyof Settings]?: Settings[K] } = {};

    // [field, envKey, allowZero]
    const floatFields: Array<[keyof Settings, string, boolean]> = [
      ["COMMAND_TIMEOUT", "OPENROAD_COMMAND_TIMEOUT", false],
      ["COMMAND_COMPLETION_DELAY", "OPENROAD_COMMAND_COMPLETION_DELAY", true],
      ["SESSION_IDLE_TIMEOUT", "OPENROAD_SESSION_IDLE_TIMEOUT", false],
    ];
    const intFields: Array<[keyof Settings, string, boolean]> = [
      ["DEFAULT_BUFFER_SIZE", "OPENROAD_DEFAULT_BUFFER_SIZE", false],
      ["MAX_SESSIONS", "OPENROAD_MAX_SESSIONS", false],
      ["SESSION_QUEUE_SIZE", "OPENROAD_SESSION_QUEUE_SIZE", false],
      ["READ_CHUNK_SIZE", "OPENROAD_READ_CHUNK_SIZE", false],
      ["IMAGE_MAX_BASE64_KB", "OPENROAD_IMAGE_MAX_BASE64_KB", false],
      ["IMAGE_MAX_DIMENSION", "OPENROAD_IMAGE_MAX_DIMENSION", false],
      ["IMAGE_MIN_DIMENSION", "OPENROAD_IMAGE_MIN_DIMENSION", false],
      ["MAX_FLOW_JOBS", "OPENROAD_MAX_FLOW_JOBS", false],
      ["FLOW_RUN_TIMEOUT", "OPENROAD_FLOW_RUN_TIMEOUT", false],
      ["OUTPUT_HISTORY_CHARS", "OPENROAD_OUTPUT_HISTORY_CHARS", true],
      ["OUTPUT_HISTORY_COMMANDS", "OPENROAD_OUTPUT_HISTORY_COMMANDS", true],
    ];
    const strFields: Array<[keyof Settings, string]> = [
      ["LOG_LEVEL", "LOG_LEVEL"],
      ["LOG_FORMAT", "LOG_FORMAT"],
      ["ORFS_FLOW_PATH", "ORFS_FLOW_PATH"],
      ["QOR_API_URL", "OPENROAD_QOR_API_URL"],
      ["RUN_LOG_DIR", "OPENROAD_RUN_LOG_DIR"],
    ];

    for (const [field, envKey, allowZero] of floatFields) {
      const val = process.env[envKey];
      if (val !== undefined) (overrides as Record<string, unknown>)[field] = parseFloat_(envKey, val, allowZero);
    }
    for (const [field, envKey, allowZero] of intFields) {
      const val = process.env[envKey];
      if (val !== undefined) (overrides as Record<string, unknown>)[field] = parseInt_(envKey, val, allowZero);
    }
    for (const [field, envKey] of strFields) {
      const val = process.env[envKey];
      if (val !== undefined && val.trim() !== "") (overrides as Record<string, unknown>)[field] = val;
    }

    const allowedCommandsEnv = process.env["OPENROAD_ALLOWED_COMMANDS"];
    if (allowedCommandsEnv !== undefined) {
      const cmds = allowedCommandsEnv.split(",").map((s) => s.trim()).filter((s) => s.length > 0);
      if (cmds.length > 0) overrides.ALLOWED_COMMANDS = cmds;
    }

    const enableValidationEnv = process.env["OPENROAD_ENABLE_COMMAND_VALIDATION"];
    if (enableValidationEnv !== undefined) {
      overrides.ENABLE_COMMAND_VALIDATION = parseBool("OPENROAD_ENABLE_COMMAND_VALIDATION", enableValidationEnv);
    }

    const whitelistEnabledEnv = process.env["OPENROAD_WHITELIST_ENABLED"];
    if (whitelistEnabledEnv !== undefined) {
      overrides.WHITELIST_ENABLED = parseBool("OPENROAD_WHITELIST_ENABLED", whitelistEnabledEnv);
    }

    return new Settings(overrides);
  }
}

let _cachedSettings: Settings | null = null;

export function initSettings(): Settings {
  try {
    _cachedSettings = Settings.fromEnv();
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    throw new Error(`Failed to initialise settings from environment variables: ${msg}`);
  }
  return _cachedSettings;
}

export function getSettings(): Settings {
  return _cachedSettings ?? initSettings();
}
