import org.gradle.api.file.Directory
import org.gradle.api.tasks.Delete

allprojects {
    repositories {
        google()
        mavenCentral()
    }
}

val sharedBuildDirectory: Directory = rootProject.layout.buildDirectory
    .dir("../../build")
    .get()
rootProject.layout.buildDirectory.set(sharedBuildDirectory)

subprojects {
    val sharedSubprojectBuildDirectory: Directory = sharedBuildDirectory.dir(project.name)
    project.layout.buildDirectory.set(sharedSubprojectBuildDirectory)
}

subprojects {
    project.evaluationDependsOn(":app")
}

tasks.register<Delete>("clean") {
    delete(rootProject.layout.buildDirectory)
}
