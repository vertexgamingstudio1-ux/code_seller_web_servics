class VersionService:
    @staticmethod
    def list_versions():
        return {"status": "pending_database", "versions": [], "count": 0}
    @staticmethod
    def get_version(version_id):
        return {"status": "pending_database", "version_id": version_id}
    @staticmethod
    def create_version(data):
        return {"status": "pending_database", "message": "Version creation ready.", "data": data}
