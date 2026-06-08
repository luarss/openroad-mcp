import path from "node:path";
import fs from "node:fs";
import { ValidationError } from "../exceptions.js";

export function validatePathSegment(segment: string, segmentName: string): void {
  if (!segment) throw new ValidationError(`${segmentName} cannot be empty`);
  if (segment === "." || segment === "..") throw new ValidationError(`${segmentName} cannot be '.' or '..'`);
  if (segment.includes("/") || segment.includes("\\")) throw new ValidationError(`${segmentName} cannot contain path separators`);
  if (segment.includes("\x00")) throw new ValidationError(`${segmentName} cannot contain null bytes`);
  if (/[*?[\]]/.test(segment)) throw new ValidationError(`${segmentName} cannot contain glob characters (* ? [ ])`);
}

export function validateSafePathContainment(targetPath: string, basePath: string, context: string): void {
  let resolvedTarget: string;
  let resolvedBase: string;

  try {
    resolvedBase = fs.realpathSync(basePath);
  } catch (e) {
    throw new ValidationError(`Failed to resolve ${context} path: ${e}`);
  }

  try {
    // For non-existing paths (ENOENT), fall back to path.resolve.
    resolvedTarget = fs.realpathSync(targetPath);
  } catch (e) {
    if ((e as NodeJS.ErrnoException).code === "ENOENT") {
      resolvedTarget = path.resolve(targetPath);
    } else {
      throw new ValidationError(`Failed to resolve ${context} path: ${e}`);
    }
  }

  const rel = path.relative(resolvedBase, resolvedTarget);
  if (rel.startsWith("..") || path.isAbsolute(rel)) {
    throw new ValidationError(`${context} path ${targetPath} is not contained within ${basePath}`);
  }
}
