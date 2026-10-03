"""Offline Google SDK boundary double; never contacts Google or persists real tokens."""

import json
import re
from datetime import UTC, datetime, timedelta

import httplib2
from google.oauth2.credentials import Credentials
from googleapiclient.errors import HttpError

from app.services.storage.google_client import FOLDER_MIME, SCOPES


def http_error(status: int, reason: str = "forbidden") -> HttpError:
    return HttpError(
        httplib2.Response({"status": str(status)}),
        json.dumps({"error": {"errors": [{"reason": reason}]}}).encode(),
    )


def credentials() -> Credentials:
    return Credentials(
        "test-access-token",
        refresh_token="test-refresh-token",
        token_uri="https://oauth2.googleapis.com/token",
        client_id="test-client",
        client_secret="test-client-secret",
        scopes=SCOPES,
        expiry=(datetime.now(UTC) + timedelta(hours=1)).replace(tzinfo=None),
    )


class Request:
    def __init__(self, action):
        self.action = action

    def execute(self, **kwargs):
        return self.action()


class Upload:
    def __init__(self, drive, body, media):
        self.drive, self.body, self.media = drive, body, media
        self.chunks = 0

    def next_chunk(self, **kwargs):
        self.drive.network("upload")
        self.chunks += 1
        if self.chunks == 1:
            return self, None
        item = self.body | {"size": str(self.media.size()), "mimeType": self.media.mimetype()}
        self.drive.objects[item["id"]] = item
        self.media.stream().seek(0)
        self.drive.uploaded_bytes = self.media.stream().read()
        if self.drive.after_upload:
            self.drive.after_upload()
        return None, {"id": item["id"], "size": item["size"]}

    def progress(self):
        return 0.5


class FakeDrive:
    def __init__(self, engine=None):
        self.engine = engine
        self.objects = {
            "root-folder": {
                "id": "root-folder",
                "name": "VideoVault",
                "mimeType": FOLDER_MIME,
                "capabilities": {"canAddChildren": True},
                "parents": ["root"],
            }
        }
        self.identity = "test-account"
        self.calls = []
        self.queries = []
        self.errors = {}
        self.after_upload = None
        self.uploaded_bytes = b""
        self.serial = 0

    def network(self, operation):
        if self.engine:
            assert self.engine.pool.checkedout() == 0, "Google I/O held a DB transaction"
        self.calls.append(operation)
        if self.errors.get(operation):
            raise self.errors[operation].pop(0)

    def files(self):
        return self

    def about(self):
        return self

    def get(self, fileId=None, **kwargs):
        def action():
            self.network("get" if fileId else "about")
            if fileId is None:
                return {"user": {"permissionId": self.identity, "displayName": "Test account"}}
            if fileId not in self.objects:
                raise http_error(404)
            return self.objects[fileId].copy()

        return Request(action)

    def list(self, q, **kwargs):
        def action():
            self.network("list")
            self.queries.append(q)
            parent = q.split("'", 2)[1]
            name = re.search(r"name = '(.*)'$", q)[1].replace("\\'", "'").replace("\\\\", "\\")
            return {
                "files": [
                    item.copy()
                    for item in self.objects.values()
                    if parent in item.get("parents", [])
                    and item["name"] == name
                    and item["mimeType"] == FOLDER_MIME
                    and not item.get("trashed")
                ]
            }

        return Request(action)

    def create(self, body, media_body=None, **kwargs):
        if media_body:
            assert media_body.resumable() and media_body.chunksize() == 1024 * 1024
            return Upload(self, body, media_body)

        def action():
            self.network("create-folder")
            self.serial += 1
            item = body | {"id": f"folder-{self.serial}", "capabilities": {"canAddChildren": True}}
            self.objects[item["id"]] = item
            return item.copy()

        return Request(action)

    def generateIds(self, **kwargs):
        def action():
            self.network("generate-id")
            self.serial += 1
            return {"ids": [f"media-{self.serial}"]}

        return Request(action)

    def delete(self, fileId, **kwargs):
        def action():
            self.network("delete")
            self.objects.pop(fileId, None)
            return {}

        return Request(action)

    def close(self):
        pass


class FakeFlow:
    credentials = credentials()

    def authorization_url(self, **kwargs):
        return "https://accounts.google.com/o/oauth2/auth?state=" + kwargs["state"], kwargs["state"]

    def fetch_token(self, **kwargs):
        assert kwargs["timeout"] == 30


def connect(storage, drive):
    connection = storage.connection
    connection.client_factory = lambda creds: drive

    def flow_factory(config, **kwargs):
        assert kwargs["autogenerate_code_verifier"] is True
        assert kwargs["scopes"] == SCOPES
        return FakeFlow()

    connection.flow_factory = flow_factory
    connection.start()
    connection.callback(next(iter(connection.states)), "test-code", None)
    storage.drive.set_root("root-folder")
