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
    smithyBuild("software.amazon.smithy:smithy-aws-traits:1.69.0")
    smithyBuild("software.amazon.smithy:smithy-aws-apigateway-traits:1.69.0")
    smithyBuild("software.amazon.smithy:smithy-validation-model:1.69.0")
    smithyBuild("software.amazon.smithy:smithy-openapi:1.69.0")
    smithyBuild("software.amazon.smithy:smithy-aws-apigateway-openapi:1.69.0")
}
