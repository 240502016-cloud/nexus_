const SUPPORTED_IMAGE_TYPES = new Map([
  ["image/png", "png"],
  ["image/jpeg", "jpg"],
  ["image/gif", "gif"],
  ["image/webp", "webp"],
]);

function firstClipboardImage(data: DataTransfer): File | null {
  for (const item of Array.from(data.items)) {
    if (item.kind !== "file" || !item.type.toLowerCase().startsWith("image/")) continue;
    const file = item.getAsFile();
    if (file) return file;
  }
  return Array.from(data.files).find((file) => file.type.toLowerCase().startsWith("image/")) ?? null;
}

/**
 * Panodaki ilk güvenli, backend'in satır içinde gösterebildiği görseli bir dosyaya çevirir.
 * Metin panolarında null döner; böylece textarea'nın normal yapıştırma davranışı korunur.
 */
export function clipboardImageFile(data: DataTransfer, now = new Date()): File | null {
  const source = firstClipboardImage(data);
  if (!source) return null;

  const type = source.type.toLowerCase();
  const extension = SUPPORTED_IMAGE_TYPES.get(type);
  if (!extension) return null;

  const timestamp = now.toISOString().replace(/[:.]/g, "-");
  return new File([source], `pano-${timestamp}.${extension}`, {
    type,
    lastModified: now.getTime(),
  });
}
