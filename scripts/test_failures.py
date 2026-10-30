import subprocess


FAILURES = [
    "schema_change",
    "data_quality",
    "configuration_error",
    "dependency_error",
]


for failure in FAILURES:
    print("\n" + "=" * 60)
    print(f"Testing: {failure}")
    print("=" * 60)

    result = subprocess.run(
        [
            "python",
            "-m",
            "pipeline.runner",
            "--failure",
            failure
        ],
        text=True
    )

    print(f"Exit code: {result.returncode}")