class VoiceDirectorError(Exception):
    """Expected, user-correctable input or contract error."""


class ValidationError(VoiceDirectorError):
    pass


class OutputExistsError(VoiceDirectorError):
    pass


class HumanReviewRequired(VoiceDirectorError):
    """The bundle contains uncertainties that need an explicit user decision."""

    def __init__(self, report):
        super().__init__(report.get("status", "human review required"))
        self.report = report
