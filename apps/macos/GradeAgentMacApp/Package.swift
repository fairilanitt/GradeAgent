// swift-tools-version: 6.0

import PackageDescription

let package = Package(
    name: "GradeAgentMacApp",
    platforms: [
        .macOS(.v14),
    ],
    products: [
        .executable(name: "GradeAgentMacApp", targets: ["GradeAgentMacApp"]),
    ],
    targets: [
        .executableTarget(
            name: "GradeAgentMacApp",
            path: "Sources/GradeAgentMacApp"
        ),
    ]
)
