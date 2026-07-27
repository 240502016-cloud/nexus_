import { formatFileSize } from "../messageContent";
import type { Attachment } from "../types";
import { Icon } from "./Icon";

export function AttachmentCard({ attachment, caption }: { attachment: Attachment; caption?: string }) {
  return (
    <div className="attachment-card">
      {attachment.is_image ? (
        <a href={attachment.url} target="_blank" rel="noreferrer">
          <img src={attachment.url} alt={attachment.name} loading="lazy" />
        </a>
      ) : (
        <a className="attachment-card__file" href={attachment.url} download={attachment.name}>
          <Icon name="file" />
          <span><strong>{attachment.name}</strong><small>{formatFileSize(attachment.size)}</small></span>
        </a>
      )}
      {caption ? <p>{caption}</p> : null}
    </div>
  );
}
