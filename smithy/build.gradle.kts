plugins {
    `java-library`
    id("software.amazon.smithy.gradle.smithy-jar") version "1.4.0"
}

repositories {
    mavenCentral()
}

smithy {
    outputDirectory.set(file("../build/smithy"))
}

dependencies {
    smithyBuild("software.amazon.smithy:smithy-aws-traits:1.68.0")
    smithyBuild("software.amazon.smithy:smithy-aws-apigateway-traits:1.67.0")
    smithyBuild("software.amazon.smithy:smithy-validation-model:1.67.0")
    smithyBuild("software.amazon.smithy:smithy-openapi:1.67.0")
    smithyBuild("software.amazon.smithy:smithy-aws-apigateway-openapi:1.67.0")
}
