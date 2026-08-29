import sys
import types

sys.modules.setdefault("boto3", types.ModuleType("boto3"))
