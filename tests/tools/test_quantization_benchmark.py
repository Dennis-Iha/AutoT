from tools.quantization_benchmark import discover_models


def test_discover_models_returns_list_of_label_path_pairs():
    models = discover_models()
    assert isinstance(models, list)
    for label, path in models:
        assert isinstance(label, str)
        assert path.suffix == ".bin"


def test_discover_models_base_label_first_when_present():
    models = discover_models()
    labels = [label for label, _ in models]
    if "base (unquantized, f16)" in labels:
        assert labels[0] == "base (unquantized, f16)"
