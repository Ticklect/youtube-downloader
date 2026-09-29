import { createHash } from "node:crypto";

export function deriveExtensionId(manifestKeyBase64) {
  if (typeof manifestKeyBase64 !== "string" || !manifestKeyBase64.trim()) {
    throw new TypeError("manifest key must be a non-empty base64 string");
  }

  const publicKeyBytes = Buffer.from(manifestKeyBase64, "base64");
  if (publicKeyBytes.length === 0) {
    throw new TypeError("manifest key did not decode to public-key bytes");
  }

  const digest = createHash("sha256").update(publicKeyBytes).digest();
  let extensionId = "";
  for (const byte of digest.subarray(0, 16)) {
    extensionId += String.fromCharCode(97 + (byte >> 4));
    extensionId += String.fromCharCode(97 + (byte & 0x0f));
  }
  return extensionId;
}
