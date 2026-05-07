import { getEnv } from "./env.js";

export type TorrentFileMetadata = {
  path: string;
  sizeBytes: number;
};

export type TorrentMetadata = {
  name: string;
  sizeBytes: number;
  files: TorrentFileMetadata[];
  raw: Uint8Array;
};

export interface TorrentMetadataProvider {
  fetch(infoHash: string): Promise<TorrentMetadata>;
}

export class FakeTorrentMetadataProvider implements TorrentMetadataProvider {
  async fetch(infoHash: string): Promise<TorrentMetadata> {
    const files = [{ path: `${infoHash.slice(0, 8)}.mp4`, sizeBytes: 1024 }];
    return {
      name: `Fixture ${infoHash.slice(0, 8)}`,
      sizeBytes: files.reduce((total, file) => total + file.sizeBytes, 0),
      files,
      raw: new TextEncoder().encode(`d4:info${infoHash}e`),
    };
  }
}

export class HttpTorrentMetadataProvider implements TorrentMetadataProvider {
  constructor(
    private readonly resolverUrls: string[],
    private readonly timeoutSeconds: number,
  ) {}

  async fetch(infoHash: string): Promise<TorrentMetadata> {
    if (this.resolverUrls.length === 0) {
      throw new Error("No torrent resolver URLs are configured.");
    }

    let lastError: unknown;
    for (const resolverUrl of this.resolverUrls) {
      try {
        const response = await fetch(this.resolveUrl(resolverUrl, infoHash), {
          headers: { "User-Agent": "MyMediaVault/0.1" },
          signal: AbortSignal.timeout(this.timeoutSeconds * 1000),
        });
        if (!response.ok) {
          throw new Error(`Resolver returned ${response.status}`);
        }
        const raw = new Uint8Array(await response.arrayBuffer());
        return await parseTorrent(raw);
      } catch (error) {
        lastError = error;
      }
    }
    throw new Error("Unable to fetch a valid .torrent payload", { cause: lastError });
  }

  private resolveUrl(resolverUrl: string, infoHash: string) {
    return resolverUrl.includes("{info_hash}")
      ? resolverUrl.replace("{info_hash}", infoHash)
      : `${resolverUrl.replace(/\/$/, "")}/${infoHash}`;
  }
}

export function buildTorrentProvider(): TorrentMetadataProvider {
  const env = getEnv();
  return env.torrentProvider === "http"
    ? new HttpTorrentMetadataProvider(env.torrentResolverUrls, env.torrentFetchTimeoutSeconds)
    : new FakeTorrentMetadataProvider();
}

async function parseTorrent(raw: Uint8Array): Promise<TorrentMetadata> {
  const { default: bencode } = await import("bencode");
  const decoded = bencode.decode(Buffer.from(raw)) as Record<string, unknown>;
  const info = decoded.info as Record<string, unknown> | undefined;
  if (!info) {
    throw new Error("Torrent payload is missing an info dictionary.");
  }

  const name = decodeText(info.name ?? "unknown");
  const filesValue = info.files;
  const files: TorrentFileMetadata[] = Array.isArray(filesValue)
    ? filesValue.map((item, index) => {
        const record = item as Record<string, unknown>;
        const pathValue = Array.isArray(record.path)
          ? record.path.map((segment) => decodeText(segment)).join("/")
          : `${name}/${index}`;
        return {
          path: pathValue,
          sizeBytes: toNumber(record.length),
        };
      })
    : [{ path: name, sizeBytes: toNumber(info.length) }];

  return {
    name,
    sizeBytes: files.reduce((total, file) => total + file.sizeBytes, 0),
    files,
    raw,
  };
}

function decodeText(value: unknown) {
  if (typeof value === "string") {
    return value;
  }
  if (value instanceof Uint8Array) {
    return new TextDecoder().decode(value);
  }
  return "unknown";
}

function toNumber(value: unknown) {
  if (typeof value === "number") {
    return value;
  }
  if (typeof value === "bigint") {
    return Number(value);
  }
  if (value instanceof Uint8Array) {
    return Number(new TextDecoder().decode(value));
  }
  return 0;
}
