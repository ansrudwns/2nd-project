import logging
import traceback
from typing import Callable, Any, Dict, List
from app.core.exceptions import AnalysisException, Stage
from app.schemas.common import BaseResponse, create_error_response

logger = logging.getLogger(__name__)

Context = Dict[str, Any]

class PipelineRunner:
    def __init__(self):
        self.context: Context = {}

    async def run_stage(self, stage: Stage, func: Callable[..., Any], *args, **kwargs):
        """
        Executes a single stage. If it raises an exception, the pipeline stops.
        """
        try:
            logger.info(f"Starting Stage: {stage.value}")
            result = await func(*args, **kwargs)
            logger.info(f"Completed Stage: {stage.value}")
            return result
        except AnalysisException as e:
            # Re-raise known exceptions to be caught by the main runner
            logger.error(f"AnalysisException in {stage.value}: {e.message}")
            raise e
        except Exception as e:
            # Wrap unknown exceptions
            logger.error(f"Unexpected error in {stage.value}: {str(e)}")
            logger.error(traceback.format_exc())
            raise AnalysisException(
                stage=stage,
                code=f"{stage.value}_SYSTEM_ERROR",
                message="시스템 내부 오류가 발생했습니다.",
                detail={"original_error": str(e)},
                action="잠시 후 다시 시도해주세요."
            )

    async def execute(self, steps: List[Callable[[Context], Any]]):
        """
        Execute a list of steps sequentially.
        Each step function should take 'context' dict as the first argument, 
        and return updated context or None.
        """
        try:
            for step_func in steps:
                # Check for client disconnection
                req = self.context.get("request")
                if req and await req.is_disconnected():
                    logger.info("Pipeline cancelled by client disconnection.")
                    # Abort pipeline execution
                    return BaseResponse(success=False, error="Cancelled by user")

                # We assume steps are async or wrapped properly if strictly needed, 
                # but here we allow simple awaits.
                # The step function itself should handle reading/writing to self.context
                if hasattr(step_func, 'stage_id'):
                     stage_id = step_func.stage_id
                else:
                     stage_id = Stage.SYSTEM # Default if not tagged
                
                # Execute
                await self.run_stage(stage_id, step_func, self.context)

            return BaseResponse(success=True, data=self.context.get("result"))

        except AnalysisException as e:
            await self.cleanup()
            return create_error_response(e.stage, e.code, e.message, e.detail, e.action)
        except Exception as e:
            await self.cleanup()
            # This catch-all should ideally not be reached due to run_stage wrapping, 
            # but for safety in the runner loop itself.
            return create_error_response(
                Stage.SYSTEM, 
                "CRITICAL_FAILURE", 
                "알 수 없는 치명적 오류가 발생했습니다.", 
                {"detail": str(e)},
                "관리자에게 문의하세요."
            )

    async def cleanup(self):
        """
        Clean up resources (temp files, etc.) on failure.
        """
        logger.info("Executing Pipeline Cleanup...")
        # Implement cleanup logic here (e.g. deleting temp files from context paths)
        try:
           temp_files = self.context.get("temp_files", [])
           for f in temp_files:
               # os.remove(f) ...
               pass
        except Exception as e:
            logger.warning(f"Cleanup failed: {e}")

# Decorator to tag functions with stage
def pipeline_stage(stage: Stage):
    def decorator(func):
        func.stage_id = stage
        return func
    return decorator
