$version: "2"

namespace layertwo.syncstorage

@error("client")
@httpError(409)
structure ConflictException {
    @required
    message: String
}

@error("client")
@httpError(412)
structure PreconditionFailedException {
    @required
    message: String
}

@error("client")
@httpError(413)
structure RequestTooLargeException {
    @required
    message: String
}

@error("client")
@httpError(429)
structure QuotaExceededException {
    @required
    message: String
}

@error("client")
@httpError(404)
structure CollectionNotFoundException {
    @required
    message: String
}

@error("client")
@httpError(401)
structure AuthenticationException {
    @required
    message: String
}