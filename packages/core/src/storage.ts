import { BlobServiceClient } from "@azure/storage-blob";
import { QueueClient } from "@azure/storage-queue";
import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { getEnv } from "./env.js";

export interface BlobStore {
  putBytes(key: string, data: Uint8Array): Promise<string>;
  getBytes(key: string): Promise<Uint8Array>;
  deleteIfExists(key: string): Promise<void>;
}

export interface QueueStore {
  sendJson(queueName: string, payload: unknown): Promise<void>;
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

  async deleteIfExists(key: string) {
    await rm(path.join(this.root, key), { force: true });
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

  async deleteIfExists(key: string) {
    await this.container.deleteBlob(key).catch(() => undefined);
  }
}

class AzureQueueStore implements QueueStore {
  constructor(private readonly connectionString: string) {}

  async sendJson(queueName: string, payload: unknown) {
    const queue = new QueueClient(this.connectionString, queueName);
    await queue.createIfNotExists();
    await queue.sendMessage(JSON.stringify(payload));
  }
}

export function buildBlobStore(): BlobStore {
  const env = getEnv();
  if (env.azureStorageConnectionString) {
    return new AzureBlobStore(env.azureStorageConnectionString, env.azureBlobContainer);
  }
  return new FileSystemBlobStore(path.join(process.cwd(), ".local", "blob-storage"));
}

export function buildQueueStore(): QueueStore {
  const env = getEnv();
  const connectionString = env.azureStorageConnectionString ?? env.azureWebJobsStorage;
  if (!connectionString) {
    throw new Error("Missing MMV_AZURE_STORAGE_CONNECTION_STRING or AzureWebJobsStorage for queue operations.");
  }
  return new AzureQueueStore(connectionString);
}
