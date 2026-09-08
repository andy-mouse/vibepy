"""An object that looks describable and is not an App entrypoint."""


class Impostor:
    def describe(self) -> str:
        return "not an AppDescription"


IMPOSTOR = Impostor()
