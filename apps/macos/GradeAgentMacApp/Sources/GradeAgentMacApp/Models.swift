import Foundation

struct GuiPromptTemplate: Codable, Identifiable, Hashable {
    let promptId: String
    var title: String
    var body: String
    var modelProvider: String
    var modelName: String
    var reasoningLevel: String
    var builtIn: Bool

    var id: String { promptId }

    private enum CodingKeys: String, CodingKey {
        case promptId
        case title
        case body
        case modelProvider
        case modelName
        case reasoningLevel
        case builtIn
    }

    init(
        promptId: String,
        title: String,
        body: String,
        modelProvider: String = "vertex_ai",
        modelName: String = "gemini-3.1-pro-preview",
        reasoningLevel: String = "medium",
        builtIn: Bool
    ) {
        self.promptId = promptId
        self.title = title
        self.body = body
        self.modelProvider = modelProvider
        self.modelName = modelName
        self.reasoningLevel = reasoningLevel
        self.builtIn = builtIn
    }

    init(from decoder: any Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        promptId = try container.decode(String.self, forKey: .promptId)
        title = try container.decode(String.self, forKey: .title)
        body = try container.decode(String.self, forKey: .body)
        modelProvider = try container.decodeIfPresent(String.self, forKey: .modelProvider) ?? "vertex_ai"
        modelName = try container.decodeIfPresent(String.self, forKey: .modelName) ?? "gemini-3.1-pro-preview"
        reasoningLevel = try container.decodeIfPresent(String.self, forKey: .reasoningLevel) ?? "medium"
        builtIn = try container.decodeIfPresent(Bool.self, forKey: .builtIn) ?? false
    }
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
    let observedScores: [GuiOverviewObservedScore]

    private enum CodingKeys: String, CodingKey {
        case assignmentTitle
        case groupName
        case studentsAnsweredCount
        case studentsTotalCount
        case exercises
        case observedScores
    }

    init(
        assignmentTitle: String,
        groupName: String?,
        studentsAnsweredCount: Int?,
        studentsTotalCount: Int?,
        exercises: [GuiExerciseColumn],
        observedScores: [GuiOverviewObservedScore] = []
    ) {
        self.assignmentTitle = assignmentTitle
        self.groupName = groupName
        self.studentsAnsweredCount = studentsAnsweredCount
        self.studentsTotalCount = studentsTotalCount
        self.exercises = exercises
        self.observedScores = observedScores
    }

    init(from decoder: any Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        assignmentTitle = try container.decodeIfPresent(String.self, forKey: .assignmentTitle) ?? ""
        groupName = try container.decodeIfPresent(String.self, forKey: .groupName)
        studentsAnsweredCount = try container.decodeIfPresent(Int.self, forKey: .studentsAnsweredCount)
        studentsTotalCount = try container.decodeIfPresent(Int.self, forKey: .studentsTotalCount)
        exercises = try container.decodeIfPresent([GuiExerciseColumn].self, forKey: .exercises) ?? []
        observedScores = try container.decodeIfPresent([GuiOverviewObservedScore].self, forKey: .observedScores) ?? []
    }
}

struct GuiOverviewObservedScore: Codable, Identifiable, Hashable {
    let selectorIndex: Int
    let studentName: String
    let scoreText: String
    let scoreAwarded: Double?
    let scorePossible: Double?
    let reviewed: Bool
    let categoryName: String?
    let exerciseLabel: String?
    let exerciseNumber: String?

    var id: String {
        [
            "\(selectorIndex)",
            studentName,
            categoryName ?? "",
            exerciseLabel ?? "",
            exerciseNumber ?? "",
            scoreText,
        ].joined(separator: "|")
    }
}

struct GuiGradeExerciseRequest: Codable {
    let columnKey: String
    let instructions: String
    let promptId: String?
    let promptTitle: String?
    let modelProvider: String?
    let modelName: String?
    let reasoningLevel: String?
    let maxSteps: Int
}

struct GuiPromptSaveRequest: Codable {
    let promptId: String?
    let title: String
    let body: String
    let modelProvider: String
    let modelName: String
    let reasoningLevel: String
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
    let overview: GuiOverviewResponse
}

struct GuiAutopilotQueueItemRequest: Codable, Identifiable, Hashable {
    let columnKey: String
    let instructions: String
    let promptId: String?
    let promptTitle: String?
    let modelProvider: String?
    let modelName: String?
    let reasoningLevel: String?
    let maxSteps: Int

    var id: String { columnKey }
}

struct GuiAutopilotQueueItemResult: Codable, Identifiable {
    let columnKey: String
    let exerciseTitle: String?
    let promptId: String?
    let promptTitle: String?
    let result: ExamSessionGradingTaskResult

    var id: String { "\(columnKey)|\(result.jobId)" }
}

struct GuiAutopilotRunRequest: Codable {
    let items: [GuiAutopilotQueueItemRequest]
}

struct GuiAutopilotRunResponse: Codable {
    let summary: String
    let items: [GuiAutopilotQueueItemResult]
    let overview: GuiOverviewResponse
}

struct GuiGradebookQueryRequest: Codable {
    let question: String
}

struct GuiGradebookExerciseScore: Decodable, Identifiable, Hashable {
    let categoryName: String?
    let exerciseLabel: String?
    let exerciseNumber: String?
    let scoreText: String
    let scoreAwarded: Double?
    let scorePossible: Double?
    let reviewed: Bool

    var id: String {
        [
            categoryName ?? "",
            exerciseLabel ?? "",
            exerciseNumber ?? "",
            scoreText,
        ].joined(separator: "|")
    }
}

struct GuiGradebookExamResult: Decodable, Identifiable, Hashable {
    let assignmentTitle: String
    let assignmentDate: String
    let seriesName: String?
    let contentArea: String?
    let groupName: String?
    let statusText: String?
    let matchedStudentName: String
    let overviewURL: String
    let totalScoreAwarded: Double?
    let totalScorePossible: Double?
    let reviewedScoreCount: Int
    let exerciseScores: [GuiGradebookExerciseScore]

    private enum CodingKeys: String, CodingKey {
        case assignmentTitle
        case assignmentDate
        case seriesName
        case contentArea
        case groupName
        case statusText
        case matchedStudentName
        case overviewUrl
        case totalScoreAwarded
        case totalScorePossible
        case reviewedScoreCount
        case exerciseScores
    }

    var id: String {
        [assignmentDate, assignmentTitle, matchedStudentName].joined(separator: "|")
    }

    init(from decoder: any Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        assignmentTitle = try container.decode(String.self, forKey: .assignmentTitle)
        assignmentDate = try container.decode(String.self, forKey: .assignmentDate)
        seriesName = try container.decodeIfPresent(String.self, forKey: .seriesName)
        contentArea = try container.decodeIfPresent(String.self, forKey: .contentArea)
        groupName = try container.decodeIfPresent(String.self, forKey: .groupName)
        statusText = try container.decodeIfPresent(String.self, forKey: .statusText)
        matchedStudentName = try container.decode(String.self, forKey: .matchedStudentName)
        overviewURL = try container.decode(String.self, forKey: .overviewUrl)
        totalScoreAwarded = try container.decodeIfPresent(Double.self, forKey: .totalScoreAwarded)
        totalScorePossible = try container.decodeIfPresent(Double.self, forKey: .totalScorePossible)
        reviewedScoreCount = try container.decodeIfPresent(Int.self, forKey: .reviewedScoreCount) ?? 0
        exerciseScores = try container.decodeIfPresent([GuiGradebookExerciseScore].self, forKey: .exerciseScores) ?? []
    }
}

struct GuiGradebookQueryResponse: Decodable {
    let answerText: String
    let parserMode: String
    let modelProvider: String?
    let modelName: String?
    let examsScanned: Int
    let examsMatched: Int
    let findings: [GuiGradebookExamResult]
}

struct GuiGradebookChatMessage: Identifiable, Hashable {
    enum Role: String, Hashable {
        case user
        case assistant
    }

    let id: UUID
    let role: Role
    let text: String
    let timestamp: Date
    let findings: [GuiGradebookExamResult]
    let examsScanned: Int
    let examsMatched: Int
    let parserMode: String?
    let modelLabel: String?

    init(
        id: UUID = UUID(),
        role: Role,
        text: String,
        timestamp: Date = Date(),
        findings: [GuiGradebookExamResult] = [],
        examsScanned: Int = 0,
        examsMatched: Int = 0,
        parserMode: String? = nil,
        modelLabel: String? = nil
    ) {
        self.id = id
        self.role = role
        self.text = text
        self.timestamp = timestamp
        self.findings = findings
        self.examsScanned = examsScanned
        self.examsMatched = examsMatched
        self.parserMode = parserMode
        self.modelLabel = modelLabel
    }
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
    let reasoningLevel: String?
    let modelResponseText: String?
    let repairPromptText: String?
    let repairResponseText: String?
    let usedHeuristicFallback: Bool?
    let fallbackReason: String?
    let exerciseURL: String
    let status: String

    private enum CodingKeys: String, CodingKey {
        case studentName
        case studentProgress
        case assignmentTitle
        case groupName
        case categoryName
        case exerciseLabel
        case exerciseNumber
        case objectiveText
        case targetText
        case questionText
        case answerText
        case modelAnswerText
        case pointsText
        case scoreAwarded
        case scorePossible
        case basisLines
        case promptTemplateText
        case renderedInstructionsText
        case submittedPromptText
        case modelProvider
        case modelName
        case reasoningLevel
        case modelResponseText
        case repairPromptText
        case repairResponseText
        case usedHeuristicFallback
        case fallbackReason
        case exerciseUrl
        case status
    }

    init(from decoder: any Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        studentName = try container.decode(String.self, forKey: .studentName)
        studentProgress = try container.decodeIfPresent(String.self, forKey: .studentProgress)
        assignmentTitle = try container.decode(String.self, forKey: .assignmentTitle)
        groupName = try container.decodeIfPresent(String.self, forKey: .groupName)
        categoryName = try container.decodeIfPresent(String.self, forKey: .categoryName)
        exerciseLabel = try container.decodeIfPresent(String.self, forKey: .exerciseLabel)
        exerciseNumber = try container.decodeIfPresent(String.self, forKey: .exerciseNumber)
        objectiveText = try container.decode(String.self, forKey: .objectiveText)
        targetText = try container.decode(String.self, forKey: .targetText)
        questionText = try container.decode(String.self, forKey: .questionText)
        answerText = try container.decode(String.self, forKey: .answerText)
        modelAnswerText = try container.decode(String.self, forKey: .modelAnswerText)
        pointsText = try container.decode(String.self, forKey: .pointsText)
        scoreAwarded = try container.decodeIfPresent(Double.self, forKey: .scoreAwarded)
        scorePossible = try container.decodeIfPresent(Double.self, forKey: .scorePossible)
        basisLines = try container.decodeIfPresent([String].self, forKey: .basisLines) ?? []
        promptTemplateText = try container.decodeIfPresent(String.self, forKey: .promptTemplateText)
        renderedInstructionsText = try container.decodeIfPresent(String.self, forKey: .renderedInstructionsText)
        submittedPromptText = try container.decodeIfPresent(String.self, forKey: .submittedPromptText)
        modelProvider = try container.decodeIfPresent(String.self, forKey: .modelProvider)
        modelName = try container.decodeIfPresent(String.self, forKey: .modelName)
        reasoningLevel = try container.decodeIfPresent(String.self, forKey: .reasoningLevel)
        modelResponseText = try container.decodeIfPresent(String.self, forKey: .modelResponseText)
        repairPromptText = try container.decodeIfPresent(String.self, forKey: .repairPromptText)
        repairResponseText = try container.decodeIfPresent(String.self, forKey: .repairResponseText)
        usedHeuristicFallback = try container.decodeIfPresent(Bool.self, forKey: .usedHeuristicFallback)
        fallbackReason = try container.decodeIfPresent(String.self, forKey: .fallbackReason)
        exerciseURL = try container.decode(String.self, forKey: .exerciseUrl)
        status = try container.decode(String.self, forKey: .status)
    }

    func encode(to encoder: any Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(studentName, forKey: .studentName)
        try container.encodeIfPresent(studentProgress, forKey: .studentProgress)
        try container.encode(assignmentTitle, forKey: .assignmentTitle)
        try container.encodeIfPresent(groupName, forKey: .groupName)
        try container.encodeIfPresent(categoryName, forKey: .categoryName)
        try container.encodeIfPresent(exerciseLabel, forKey: .exerciseLabel)
        try container.encodeIfPresent(exerciseNumber, forKey: .exerciseNumber)
        try container.encode(objectiveText, forKey: .objectiveText)
        try container.encode(targetText, forKey: .targetText)
        try container.encode(questionText, forKey: .questionText)
        try container.encode(answerText, forKey: .answerText)
        try container.encode(modelAnswerText, forKey: .modelAnswerText)
        try container.encode(pointsText, forKey: .pointsText)
        try container.encodeIfPresent(scoreAwarded, forKey: .scoreAwarded)
        try container.encodeIfPresent(scorePossible, forKey: .scorePossible)
        try container.encode(basisLines, forKey: .basisLines)
        try container.encodeIfPresent(promptTemplateText, forKey: .promptTemplateText)
        try container.encodeIfPresent(renderedInstructionsText, forKey: .renderedInstructionsText)
        try container.encodeIfPresent(submittedPromptText, forKey: .submittedPromptText)
        try container.encodeIfPresent(modelProvider, forKey: .modelProvider)
        try container.encodeIfPresent(modelName, forKey: .modelName)
        try container.encodeIfPresent(reasoningLevel, forKey: .reasoningLevel)
        try container.encodeIfPresent(modelResponseText, forKey: .modelResponseText)
        try container.encodeIfPresent(repairPromptText, forKey: .repairPromptText)
        try container.encodeIfPresent(repairResponseText, forKey: .repairResponseText)
        try container.encodeIfPresent(usedHeuristicFallback, forKey: .usedHeuristicFallback)
        try container.encodeIfPresent(fallbackReason, forKey: .fallbackReason)
        try container.encode(exerciseURL, forKey: .exerciseUrl)
        try container.encode(status, forKey: .status)
    }

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
    let interrupted: Bool?
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

struct PromptModelOption: Identifiable, Hashable {
    let provider: String
    let modelName: String
    let title: String
    let subtitle: String

    var id: String { "\(provider)|\(modelName)" }
    var displayName: String { "\(title) (\(subtitle))" }
}

struct PromptReasoningOption: Identifiable, Hashable {
    let value: String
    let title: String
    let subtitle: String

    var id: String { value }
}

enum PromptEditorOptions {
    static let modelOptions: [PromptModelOption] = [
        PromptModelOption(
            provider: "vertex_ai",
            modelName: "gemini-3.1-pro-preview",
            title: "Gemini 3.1 Pro",
            subtitle: "Vertex AI Preview"
        ),
        PromptModelOption(
            provider: "vertex_ai",
            modelName: "gemini-3-pro-preview",
            title: "Gemini 3 Pro",
            subtitle: "Vertex AI Preview"
        ),
        PromptModelOption(
            provider: "vertex_ai",
            modelName: "gemini-3.1-flash-lite-preview",
            title: "Gemini 3.1 Flash-Lite",
            subtitle: "Vertex AI Preview"
        ),
        PromptModelOption(
            provider: "vertex_ai",
            modelName: "gemini-3-flash-preview",
            title: "Gemini 3 Flash",
            subtitle: "Vertex AI Preview"
        ),
        PromptModelOption(
            provider: "vertex_ai",
            modelName: "gemini-2.5-pro",
            title: "Gemini 2.5 Pro",
            subtitle: "Vertex AI"
        ),
        PromptModelOption(
            provider: "vertex_ai",
            modelName: "gemini-2.5-flash",
            title: "Gemini 2.5 Flash",
            subtitle: "Vertex AI"
        ),
        PromptModelOption(
            provider: "vertex_ai",
            modelName: "gemini-2.5-flash-lite",
            title: "Gemini 2.5 Flash-Lite",
            subtitle: "Vertex AI"
        ),
        PromptModelOption(
            provider: "vertex_ai",
            modelName: "gemini-2.5-flash-preview-09-2025",
            title: "Gemini 2.5 Flash",
            subtitle: "Vertex AI Preview 09-2025"
        ),
        PromptModelOption(
            provider: "vertex_ai",
            modelName: "gemini-2.5-flash-lite-preview-09-2025",
            title: "Gemini 2.5 Flash-Lite",
            subtitle: "Vertex AI Preview 09-2025"
        ),
        PromptModelOption(
            provider: "vertex_ai",
            modelName: "gemini-2.0-flash-001",
            title: "Gemini 2.0 Flash",
            subtitle: "Vertex AI"
        ),
        PromptModelOption(
            provider: "vertex_ai",
            modelName: "gemini-2.0-flash-lite-001",
            title: "Gemini 2.0 Flash-Lite",
            subtitle: "Vertex AI"
        ),
    ]

    static let reasoningOptions: [PromptReasoningOption] = [
        PromptReasoningOption(value: "off", title: "Pois", subtitle: "Nopein mahdollinen arviointi"),
        PromptReasoningOption(value: "low", title: "Matala", subtitle: "Kevyt päättely"),
        PromptReasoningOption(value: "medium", title: "Keskitaso", subtitle: "Tasapainoinen oletus"),
        PromptReasoningOption(value: "high", title: "Korkea", subtitle: "Tarkempi päättely"),
    ]
}
