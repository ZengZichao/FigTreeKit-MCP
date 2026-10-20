# FigTreeKit-MCP Documentation Index

[简体中文](README_CN.md) | **English**

This directory contains the technical documentation for FigTreeKit-MCP v0.1.0. Every page has a Chinese/English counterpart: Chinese is the default reading language and English is provided for international collaboration and releases. Tool parameters follow the function signatures in `src/figtreekit_mcp/tools/*.py`, `ParamSpec` in `params.py`, and the startup options in `_cli.py`.

## Reading paths

| Goal | Suggested order |
|------|-----------------|
| Install and connect a client for the first time | Root [`README_EN.md`](../README_EN.md) → [`deployment_and_client_setup_EN.md`](deployment_and_client_setup_EN.md) |
| Look up a tool's parameters, return values and error keys | [`tools_reference_EN.md`](tools_reference_EN.md) |
| Modify the source, add a tool or debug tests | [`development_guide_EN.md`](development_guide_EN.md) → [`testing_and_acceptance_EN.md`](testing_and_acceptance_EN.md) |
| Run real-data acceptance or reproduce AC/SEC checks | [`testing_and_acceptance_EN.md`](testing_and_acceptance_EN.md) |
| Run the example scripts | [`../examples/README_EN.md`](../examples/README_EN.md) |
| Understand licensing, citation and the security boundary | [`../LICENSE`](../LICENSE), [`../CITATION_EN.md`](../CITATION_EN.md), [`../SECURITY.md`](../SECURITY.md) |

## Core documents (bilingual pairs)

| Document | Chinese | English | Contents |
|----------|---------|---------|----------|
| Tool reference | [`tools_reference_CN.md`](tools_reference_CN.md) | [`tools_reference_EN.md`](tools_reference_EN.md) | Parameters, types, defaults, return keys and error keys for all 21 tools (T01–T21); 3 resources and 2 prompts; CLI startup options; multi-tree semantics; known limitations |
| Development guide | [`development_guide_CN.md`](development_guide_CN.md) | [`development_guide_EN.md`](development_guide_EN.md) | Architecture and modules, request lifecycle, adding tools, equivalence contract, security model, concurrency and error mapping, development commands |
| Deployment and client setup | [`deployment_and_client_setup_CN.md`](deployment_and_client_setup_CN.md) | [`deployment_and_client_setup_EN.md`](deployment_and_client_setup_EN.md) | Installation on three platforms, Java/JAR preparation, Claude Desktop/Cursor/VS Code configuration, SSE/Streamable HTTP, troubleshooting |
| Testing and acceptance | [`testing_and_acceptance_CN.md`](testing_and_acceptance_CN.md) | [`testing_and_acceptance_EN.md`](testing_and_acceptance_EN.md) | pytest/coverage/self-test, test data, skip semantics, equivalence probe, GTDB acceptance, AC/SEC reproduction |

## Root-level documents

| File | Chinese | English | Purpose |
|------|---------|---------|---------|
| Project overview | [`README.md`](../README.md) | [`README_EN.md`](../README_EN.md) | Project introduction, installation, running, tool table, quality and verification |
| Citation | [`CITATION_CN.md`](../CITATION_CN.md) | [`CITATION_EN.md`](../CITATION_EN.md), [`CITATION.cff`](../CITATION.cff) | Citation instructions and machine-readable metadata |
| Third-party notice | [`NOTICE_CN.md`](../NOTICE_CN.md) | [`NOTICE`](../NOTICE) | Third-party attribution; English is canonical |
| License | [`LICENSE_CN.md`](../LICENSE_CN.md) | [`LICENSE`](../LICENSE) | Chinese GPL explanation and canonical license text |
| Security policy | [`SECURITY_CN.md`](../SECURITY_CN.md) | [`SECURITY.md`](../SECURITY.md) | Security boundary and vulnerability reporting |

## Examples, scripts and tooling

| Directory | Chinese | English | Contents |
|-----------|---------|---------|----------|
| Examples | [`examples/README_CN.md`](../examples/README_CN.md) | [`examples/README_EN.md`](../examples/README_EN.md) | Runnable examples and their guides |
| Example 01: validate and summarize | [`examples/01_validate_and_summarize_CN.md`](../examples/01_validate_and_summarize_CN.md) | [`examples/01_validate_and_summarize_EN.md`](../examples/01_validate_and_summarize_EN.md) | Validation + summary workflow |
| Example 02: taxonomy audit | [`examples/02_taxonomy_audit_CN.md`](../examples/02_taxonomy_audit_CN.md) | [`examples/02_taxonomy_audit_EN.md`](../examples/02_taxonomy_audit_EN.md) | Batch monophyly audit |
| Example 03: publication figure | [`examples/03_publication_figure_CN.md`](../examples/03_publication_figure_CN.md) | [`examples/03_publication_figure_EN.md`](../examples/03_publication_figure_EN.md) | Styling + rendering |
| Scripts | [`scripts/README_CN.md`](../scripts/README_CN.md) | [`scripts/README_EN.md`](../scripts/README_EN.md) | Environment setup and launch scripts |
| Tooling | [`tools/README_CN.md`](../tools/README_CN.md) | [`tools/README_EN.md`](../tools/README_EN.md) | Equivalence probe, GTDB acceptance, MCP debug client, reference-test generator |

## Version and writing conventions

- The documentation targets **v0.1.0** (`src/figtreekit_mcp/_version.py`).
- Tool parameters follow the function signatures; defaults are also affected by `ParamSpec` in `params.py` and `AppContext` in `server.py`.
- Placeholders such as `<project-root>`, `<python>`, `<data-dir>` and `<workspace>` must be replaced with real paths; quote paths that contain spaces.
- In an error envelope, `error` is a Chinese human-readable message and `error_key` is the stable machine-readable identifier. Programmatic handling should use `code` / `error_key`.
- Real-data tests may skip when GTDB/showcase data is unavailable. "Passed" in these documents means an actually executed check, not merely an existing test.
