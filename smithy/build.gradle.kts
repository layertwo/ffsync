plugins {
    `java-library`
    id("software.amazon.smithy.gradle.smithy-jar") version "1.5.0"
}

repositories {
    mavenCentral()
}

smithy {
    outputDirectory.set(file("../build/smithy"))
}

// The models live in `models/`, declared via `sources` in smithy-build.json. The Gradle plugin
// looks in `model/` (singular) by default, so without this the model files are not task inputs:
// smithyBuild reports UP-TO-DATE after any IDL edit and silently emits stale OpenAPI specs, which
// then feed stale pydantic models into lambda/scripts/codegen.sh and a stale spec into SpecRestApi.
tasks.named("smithyBuild") {
    inputs.dir("models").withPropertyName("smithyModels").withPathSensitivity(PathSensitivity.RELATIVE)
    inputs.file("smithy-build.json").withPropertyName("smithyBuildConfig")
}

dependencies {
    smithyBuild("software.amazon.smithy:smithy-aws-traits:1.73.0")
    smithyBuild("software.amazon.smithy:smithy-aws-apigateway-traits:1.73.0")
    smithyBuild("software.amazon.smithy:smithy-validation-model:1.73.0")
    smithyBuild("software.amazon.smithy:smithy-openapi:1.73.0")
    smithyBuild("software.amazon.smithy:smithy-aws-apigateway-openapi:1.73.0")
}
