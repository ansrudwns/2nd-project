from sqlalchemy.orm import Session
from app.models.tables import Analysis, AuditLog
from app.services.storage import BlobStorageService
from typing import List, Optional
import urllib.parse
import os

storage_service = BlobStorageService()

class HistoryService:
    def create_analysis(self, db: Session, user_id: str, result: dict) -> Analysis:
        # Create new analysis record
        db_obj = Analysis(
            user_id=user_id,
            status="COMPLETED",
            result_json=result
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def get_analysis(self, db: Session, analysis_id: str) -> Optional[Analysis]:
        return db.query(Analysis).filter(Analysis.id == analysis_id).first()

    def get_user_history(self, db: Session, user_id: str, skip: int = 0, limit: int = 100) -> List[Analysis]:
        return db.query(Analysis).filter(Analysis.user_id == user_id).order_by(Analysis.created_at.desc()).offset(skip).limit(limit).all()

    def delete_analysis(self, db: Session, analysis_id: str, user_id: str) -> bool:
        analysis = db.query(Analysis).filter(Analysis.id == analysis_id, Analysis.user_id == user_id).first()
        if analysis:
            try:
                # 1. Delete Files from Blob Storage if they exist
                if analysis.result_json and "documents" in analysis.result_json:
                    docs = analysis.result_json["documents"]
                    urls_to_delete = []
                    
                    if "contract_url" in docs and docs["contract_url"]:
                        urls_to_delete.append(docs["contract_url"])
                    if "registry_url" in docs and docs["registry_url"]:
                        urls_to_delete.append(docs["registry_url"])
                        
                    for url in urls_to_delete:
                        # Extract filename from URL
                        # URL can be http://.../container/filename?sas...
                        # We need 'filename'
                        try:
                            parsed = urllib.parse.urlparse(url)
                            path = parsed.path # /history/filename
                            filename = os.path.basename(path)
                            # Filename might be URL encoded
                            filename = urllib.parse.unquote(filename)
                            
                            if filename:
                                storage_service.delete_file(filename)
                        except Exception as e:
                            print(f"Failed to delete blob for url {url}: {e}")

                # 2. Manual Cascade: Delete related AuditLogs first
                db.query(AuditLog).filter(AuditLog.analysis_id == analysis_id).delete()
                
                # 3. Delete Analysis Record
                db.delete(analysis)
                db.commit()
                return True
            except Exception as e:
                db.rollback()
                print(f"Error deleting analysis {analysis_id}: {e}")
                return False
        return False

history_service = HistoryService()
