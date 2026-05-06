import { BlobServiceClient } from "@azure/storage-blob";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { getEnv } from "./env";

export interface BlobStore {
  putBytes(key: string, data: Uint8Array): Promise<string>;
  getBytes(key: string): Promise<Uint8Array>;
}

class FileSystemBlobStore implements BlobStore {
  constructor(private readonly root: string) {}

  async putBytes(key: string, data: Uint8Array) {
    const fullPath = path.join(this.root, key);
    await mkdir(path.dirname(fullPath), { recursive: true });
    await writeFile(fullPath, data);
    return key;
  }

  async getBytes(key: string) {
    return readFile(path.join(this.root, key));
  }
}

class AzureBlobStore implements BlobStore {
  private readonly container;

  constructor(connectionString: string, containerName: string) {
    const client = BlobServiceClient.fromConnectionString(connectionString);
    this.container = client.getContainerClient(containerName);
  }

  async putBytes(key: string, data: Uint8Array) {
    await this.container.createIfNotExists();
    const blob = this.container.getBlockBlobClient(key);
    await blob.deleteIfExists();
    await blob.uploadData(data);
    return key;
  }

  async getBytes(key: string) {
    const result = await this.container.getBlobClient(key).downloadToBuffer();
    return new Uint8Array(result);
  }
}

export function buildBlobStore(): BlobStore {
  const env = getEnv();
  if (env.azureStorageConnectionString) {
    return new AzureBlobStore(env.azureStorageConnectionString, env.azureBlobContainer);
  }
  return new FileSystemBlobStore(path.join(process.cwd(), ".local", "blob-storage"));
}
