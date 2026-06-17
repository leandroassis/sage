python := "./.venv/bin/python"

[no-cd]
test: worker
    {{python}} debug_pipeline.py \
        --doc_pdf "tests/doc.pdf" \
        --req_tex "tests/test.tex" \
        --hist_pdf "tests/hist.pdf" 2>&1 | tee tests/test.log
    pkill -f "worker.py"

[no-cd]
frontend:
    {{python}} -m streamlit run frontend/app.py 2>&1 | tee logs/frontend.log &

[no-cd]
worker:
    {{python}} worker.py 2>&1 | tee logs/worker.log &

[no-cd]
clean:
    rm -rf data tests/test.log tests/fragments/*
    pkill -f "worker.py"