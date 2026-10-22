class VoiceDirectorError(Exception):
    """Expected, user-correctable input or contract error."""


class ValidationError(VoiceDirectorError):
    pass


class OutputExistsError(VoiceDirectorError):
    pass
