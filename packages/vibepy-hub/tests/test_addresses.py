"""An App's address: allocated once, derived from what is stored.

The port belongs to the installation and the hostname is the App's canonical
name (ADR-028), so the address is built rather than kept. See
`docs/decisions/ADR-031-the-proxy-is-traefik.md`.
"""

from vibepy_hub.internals.routing import PORT_BASE, address, allocate


def test_the_first_app_takes_the_base_port() -> None:
    assert allocate({}, "vibepy-todo") == PORT_BASE


def test_a_second_app_takes_the_next_free_port() -> None:
    assert allocate({"vibepy-todo": PORT_BASE}, "vibepy-notes") == PORT_BASE + 1


def test_an_app_that_already_holds_one_keeps_it() -> None:
    taken = {"vibepy-todo": PORT_BASE, "vibepy-notes": PORT_BASE + 1}
    assert allocate(taken, "vibepy-todo") == PORT_BASE


def test_a_released_port_is_taken_again_before_the_next_one() -> None:
    """Removing an App frees its port; the next install fills the gap."""
    assert allocate({"vibepy-notes": PORT_BASE + 1}, "vibepy-other") == PORT_BASE


def test_an_address_names_the_app_and_the_proxy() -> None:
    assert address("vibepy-todo", 8080) == "http://vibepy-todo.localhost:8080"
