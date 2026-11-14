#!/bin/bash
# Script for generating the test API.
# Generate pb2.py files for the gRPC client
# from protobuf files in the proto directory.

set -euo pipefail

OUT_DIR=${1:-}

if [[ -z "${OUT_DIR}" ]]; then
  echo "Usage: $0 <output_dir>" >&2
  exit 1
fi

if [[ ! -d ./proto ]]; then
  echo "Каталог ./proto не найден" >&2
  exit 1
fi

mkdir -p "${OUT_DIR}"

PROTO_LIST=$(find ./proto -name '*.proto')

PROTO_FILES=()
while IFS= read -r proto_file; do
  # An empty line means find found nothing; it is not a filename here.
  [[ -n "${proto_file}" ]] && PROTO_FILES+=("${proto_file}")
done <<<"${PROTO_LIST}"

if [[ ${#PROTO_FILES[@]} -eq 0 ]]; then
  echo "В каталоге ./proto нет ни одного .proto файла" >&2
  exit 1
fi

# protoc uses the same interpreter as the other project commands:
# the system python may not have grpcio-tools installed.
python -m grpc_tools.protoc \
  -I./proto \
  --python_out="${OUT_DIR}" \
  --grpc_python_out="${OUT_DIR}" \
  --pyi_out="${OUT_DIR}" \
  "${PROTO_FILES[@]}"

python - "${OUT_DIR}" <<'PYTHON'
import re
import sys
from pathlib import Path

output = Path(sys.argv[1])
namespace = output.name
local_packages = {path.name for path in output.iterdir() if path.is_dir() and path.name != "google"}
local_modules = {path.stem for path in output.glob("*_pb2.py")}
for path in output.rglob("*"):
    if path.suffix not in {".py", ".pyi"}:
        continue
    content = path.read_text()
    for package in local_packages:
        content = re.sub(rf"^from ({re.escape(package)}(?:\.[\w.]+)?) import", rf"from {namespace}.\1 import", content, flags=re.MULTILINE)
    for module in local_modules:
        content = re.sub(rf"^import ({re.escape(module)}) as ", rf"from {namespace} import \1 as ", content, flags=re.MULTILINE)
    content = content.replace("_Mapping]", "_Mapping[str, object]]").replace("_Mapping,", "_Mapping[str, object],")
    path.write_text(content)
PYTHON
