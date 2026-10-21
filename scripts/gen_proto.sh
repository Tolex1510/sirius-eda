#!/usr/bin/env bash
# Генерирует Python-код из proto/delivery.proto в корень проекта:
# delivery_pb2.py (сообщения), delivery_pb2_grpc.py (Stub и Servicer), delivery_pb2.pyi (типы для IDE).
#   scripts/gen_proto.sh            сгенерировать
#   scripts/gen_proto.sh <каталог>  сгенерировать в другой каталог, так тест сверяет код с контрактом
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT=${1:-$ROOT}
cd "$ROOT"
python -m grpc_tools.protoc -Iproto --python_out="$OUT" --pyi_out="$OUT" --grpc_python_out="$OUT" proto/delivery.proto
