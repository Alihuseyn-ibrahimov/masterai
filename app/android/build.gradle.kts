allprojects {
    repositories {
        google()
        mavenCentral()
    }
}

// flutter_secure_storage 11 compileSdk=37 hardcode edir; SDK-da android-37
// quraşdırılmayıbsa build sınır (bax dildostu/app/android/build.gradle.kts —
// eyni problem orada da rast gəlinib). Plugin-ləri Flutter defoltuna endiririk.
subprojects {
    afterEvaluate {
        extensions.findByType(com.android.build.gradle.LibraryExtension::class.java)
            ?.compileSdk = 36
    }
}

val newBuildDir: Directory =
    rootProject.layout.buildDirectory
        .dir("../../build")
        .get()
rootProject.layout.buildDirectory.value(newBuildDir)

subprojects {
    val newSubprojectBuildDir: Directory = newBuildDir.dir(project.name)
    project.layout.buildDirectory.value(newSubprojectBuildDir)
}
subprojects {
    project.evaluationDependsOn(":app")
}

tasks.register<Delete>("clean") {
    delete(rootProject.layout.buildDirectory)
}
