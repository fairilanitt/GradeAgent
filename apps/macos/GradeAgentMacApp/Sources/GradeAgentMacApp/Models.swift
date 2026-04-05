import Foundation

struct GuiPromptTemplate: Codable, Identifiable, Hashable {
    let promptId: String
    var title: String
    var body: String
    var builtIn: Bool

    var id: String { promptId }
}

struct GuiExerciseColumn: Codable, Identifiable, Hashable {
    let columnKey: String
    let title: String
    let categoryName: String?
    let exerciseNumber: String?
    let totalCellCount: Int
    let reviewedCellCount: Int
    let pendingCellCount: Int

    var id: String { columnKey }
}

struct GuiStateResponse: Codable {
    let browserReady: Bool
    let sessionId: String?
    let promptCount: Int
}

struct GuiBrowserStartResponse: Codable {
    let sessionId: String
    let browserReady: Bool
}

struct GuiOverviewResponse: Codable {
    let assignmentTitle: String
    let groupName: String?
    let studentsAnsweredCount: Int?
    let studentsTotalCount: Int?
    let exercises: [GuiExerciseColumn]
}

struct GuiGradeExerciseRequest: Codable {
    let columnKey: String
    let instructions: String
    let promptId: String?
    let promptTitle: String?
    let maxSteps: Int
}

struct GuiPromptSaveRequest: Codable {
    let promptId: String?
    let title: String
    let body: String
}

struct ExamSessionGradingTaskResult: Codable {
    let jobId: String
    let status: String
    let summary: String
    let currentExerciseLabel: String?
    let currentStudentName: String?
    let reportPath: String?
}

struct GuiGradeExerciseResponse: Codable {
    let result: ExamSessionGradingTaskResult
    let exercises: [GuiExerciseColumn]
}

struct GuiStatisticsEntry: Codable, Identifiable, Hashable {
    let studentName: String
    let studentProgress: String?
    let assignmentTitle: String
    let groupName: String?
    let categoryName: String?
    let exerciseLabel: String?
    let exerciseNumber: String?
    let objectiveText: String
    let targetText: String
    let questionText: String
    let answerText: String
    let modelAnswerText: String
    let pointsText: String
    let scoreAwarded: Double?
    let scorePossible: Double?
    let basisLines: [String]
    let promptTemplateText: String?
    let renderedInstructionsText: String?
    let submittedPromptText: String?
    let modelProvider: String?
    let modelName: String?
    let modelResponseText: String?
    let repairPromptText: String?
    let repairResponseText: String?
    let usedHeuristicFallback: Bool?
    let fallbackReason: String?
    let exerciseURL: String
    let status: String

    var id: String {
        [
            studentName,
            studentProgress ?? "",
            exerciseLabel ?? "",
            exerciseURL,
        ].joined(separator: "|")
    }
}

struct GuiStatisticsRun: Codable, Identifiable, Hashable {
    let runId: String
    let jobId: String
    let recordedAt: Date
    let status: String
    let summary: String
    let assignmentTitle: String
    let groupName: String?
    let categoryName: String?
    let exerciseLabel: String?
    let exerciseNumber: String?
    let studentsAnsweredCount: Int?
    let studentsTotalCount: Int?
    let processedAnswers: Int
    let filledPointFields: Int
    let reportPath: String?
    let promptId: String?
    let promptTitle: String?
    let entries: [GuiStatisticsEntry]

    var id: String { runId }
}

struct GuiStatisticsResponse: Codable {
    let runs: [GuiStatisticsRun]
}

struct ApiErrorResponse: Codable {
    let detail: String
}
