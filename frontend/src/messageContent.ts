import type { Attachment } from "./types";

const ATTACHMENT_PREFIX = "NEXUS_ATTACHMENT:";

export function composeAttachmentMessage(attachment: Attachment, caption: string): string {
  const header = `${ATTACHMENT_PREFIX}${JSON.stringify(attachment)}`;
  return caption.trim() ? `${header}\n${caption.trim()}` : header;
}

export function parseAttachmentMessage(
  content: string,
): { attachment: Attachment; caption: string } | null {
  if (!content.startsWith(ATTACHMENT_PREFIX)) return null;
  const [header, ...caption] = content.split("\n");
  try {
    const attachment = JSON.parse(header.slice(ATTACHMENT_PREFIX.length)) as Attachment;
    if (
      !attachment ||
      typeof attachment.url !== "string" ||
      !/^\/api\/attachments\/[0-9a-f]{32}$/.test(attachment.url) ||
      typeof attachment.name !== "string" ||
      typeof attachment.size !== "number"
    ) {
      return null;
    }
    return { attachment, caption: caption.join("\n") };
  } catch {
    return null;
  }
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
