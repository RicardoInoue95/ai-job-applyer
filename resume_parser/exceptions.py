class ResumeParserError(Exception):
    pass


class UnsupportedFormatError(ResumeParserError):
    pass


class ExtractionError(ResumeParserError):
    pass


class ParseError(ResumeParserError):
    pass
