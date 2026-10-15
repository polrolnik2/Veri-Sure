

def test_the_witness_does_not_re_enter_the_reference_model_stage():
    """`conforming_implementation` used to call `run_refmodel` from inside
    `_debug_turns`, which is inside `run_refmodel`: a stage re-entering itself
    from within its own repair loop. Sharing the GENERATOR is the intent; that
    was not sharing, and it is what made the witness impossible to lift into a
    stage of its own."""
    import ast
    import inspect

    from specflow.refmodel import conform

    tree = ast.parse(inspect.getsource(conform.conforming_implementation).strip())
    called = {
        node.func.id if isinstance(node.func, ast.Name) else
        getattr(node.func, "attr", "")
        for node in ast.walk(tree) if isinstance(node, ast.Call)
    }
    imported = {
        alias.name
        for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert "generate_model" in called, called
    assert "run_refmodel" not in called | imported
