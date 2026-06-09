# `action-detect-relevant-changes`

> Detects changed files between two git refs matching configurable file-type and glob filters.

## Usage

```yaml
- uses: Framework-R-D/action-detect-relevant-changes@v1  # pin to commit SHA in production
  with:
    input-name: value
```

## Inputs

| Name | Description | Required | Default |
|------|-------------|----------|---------|
| `repo-path` | Path to the checked-out repository | true | `` |
| `base-ref` | Git reference or commit hash representing the diff base | false | `` |
| `head-ref` | Git reference or commit hash representing the diff head | false | `` |
| `file-type` | File type key or list of keys (comma or newline separated) | false | `` |
| `include-globs` | Optional glob filters (comma or newline separated) | false | `` |
| `exclude-globs` | Optional glob filters to exclude (comma or newline separated) | false | `` |
| `type-pattern-add` | Additional type-to-glob mappings (comma or newline separated, e.g. cpp:*.cc). '.in' variants are added automatically. | false | `` |

## Outputs

| Name | Description |
|------|-------------|
| `matched` | true if matching files were found |
| `matched_files` | Newline-delimited list of matching files |

## License

[Apache 2.0](LICENSE)
