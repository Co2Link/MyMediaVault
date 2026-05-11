import { DeleteObjectCommand, GetObjectCommand, PutObjectCommand, S3Client } from "@aws-sdk/client-s3";
import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { getEnv } from "./env.js";

export interface BlobStore {
  putBytes(key: string, data: Uint8Array): Promise<string>;
  getBytes(key: string): Promise<Uint8Array>;
  deleteIfExists(key: string): Promise<void>;
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

class R2BlobStore implements BlobStore {
  private readonly client: S3Client;

  constructor(
    private readonly endpoint: string,
    private readonly bucketName: string,
    accessKeyId: string,
    secretAccessKey: string,
  ) {
    this.client = new S3Client({
      region: "auto",
      endpoint,
      forcePathStyle: true,
      credentials: {
        accessKeyId,
        secretAccessKey,
      },
    });
  }

  async putBytes(key: string, data: Uint8Array) {
    await this.client.send(
      new PutObjectCommand({
        Bucket: this.bucketName,
        Key: key,
        Body: data,
      }),
    );
    return key;
  }

  async getBytes(key: string) {
    const result = await this.client.send(
      new GetObjectCommand({
        Bucket: this.bucketName,
        Key: key,
      }),
    );
    const body = result.Body;
    if (!body || typeof (body as { transformToByteArray?: () => Promise<Uint8Array> }).transformToByteArray !== "function") {
      throw new Error(`Failed to read object ${key} from R2 bucket ${this.bucketName}.`);
    }
    return await (body as { transformToByteArray: () => Promise<Uint8Array> }).transformToByteArray();
  }

  async deleteIfExists(key: string) {
    await this.client.send(
      new DeleteObjectCommand({
        Bucket: this.bucketName,
        Key: key,
      }),
    );
  }
}

export function buildBlobStore(): BlobStore {
  const env = getEnv();
  if (env.r2Endpoint && env.r2AccessKeyId && env.r2SecretAccessKey) {
    return new R2BlobStore(env.r2Endpoint, env.r2BucketName, env.r2AccessKeyId, env.r2SecretAccessKey);
  }
  return new FileSystemBlobStore(path.join(process.cwd(), ".local", "blob-storage"));
}
