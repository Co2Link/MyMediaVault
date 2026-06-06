from __future__ import annotations

from datetime import datetime
from typing import Any

from beanie import Document
from pydantic import BaseModel, Field

class TorrentPreviewFrame(BaseModel):
    key: str
    width: int
    height: int
    timestampSeconds: float


class TorrentPreviewSheet(BaseModel):
    key: str
    width: int
    height: int
    mimeType: str


class TorrentPreviewDiagnostics(BaseModel):
    artifactVersion: str | None = None
    artifactFingerprint: str | None = None
    statusReason: str | None = None
    downloadedBytes: int | None = None
    elapsedSeconds: float | None = None
    selectedFilePath: str | None = None
    selectedFileSizeBytes: int | None = None
    warnings: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class Torrent(Document):
    id: str = Field(alias="_id")
    infoHash: str
    name: str | None = None
    sizeBytes: int | None = None
    rawBlobKey: str | None = None
    processingState: str = "queued"
    processingPhase: str | None = None
    processingQueuedAt: datetime | None = None
    processingAvailableAt: datetime | None = None
    processingLeaseUntil: datetime | None = None
    processingFailureCount: int = 0
    processingLastOutcome: str | None = None
    processingLastError: str | None = None
    processingUpdatedAt: datetime | None = None
    processingDiagnostics: dict[str, Any] = Field(default_factory=dict)
    files: list[dict[str, Any]] = Field(default_factory=list)
    previewFrames: list[TorrentPreviewFrame] = Field(default_factory=list)
    previewSheet: TorrentPreviewSheet | None = None
    previewDiagnostics: TorrentPreviewDiagnostics = Field(
        default_factory=TorrentPreviewDiagnostics
    )
    systemActorIds: list[str] = Field(default_factory=list)
    userActorIds: list[str] = Field(default_factory=list)
    actorAnalysisStatus: str = "pending"
    actorAnalysisAttempts: int = 0
    actorAnalysisLastAttemptAt: datetime | None = None
    actorAnalysisUpdatedAt: datetime | None = None
    actorAnalysisLeaseUntil: datetime | None = None
    actorAnalysisFingerprint: str | None = None
    actorAnalysisError: str | None = None
    actorAnalysisDiagnostics: dict[str, Any] = Field(default_factory=dict)

    class Settings:
        name = "torrents"


