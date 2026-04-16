import Foundation
import SwiftUI

enum AppPage: String, CaseIterable, Identifiable {
    case ohjaus
    case autopilot
    case kriteerit
    case tilastot
    case lokit
    case asetukset

    var id: String { rawValue }

    var title: String {
        switch self {
        case .ohjaus:
            return "Ohjaus"
        case .autopilot:
            return "Autopilot"
        case .kriteerit:
            return "Kriteerit"
        case .tilastot:
            return "Tilastot"
        case .lokit:
            return "Lokit"
        case .asetukset:
            return "Asetukset"
        }
    }

    var systemImage: String {
        switch self {
        case .ohjaus:
            return "slider.horizontal.3"
        case .autopilot:
            return "list.number"
        case .kriteerit:
            return "books.vertical"
        case .tilastot:
            return "chart.xyaxis.line"
        case .lokit:
            return "text.justify"
        case .asetukset:
            return "gearshape"
        }
    }
}

@MainActor
final class GuiStore: ObservableObject {
    private static let hideStudentNamesDefaultsKey = "gradeagent.hideStudentNamesInGui"

    @Published var selectedPage: AppPage = .ohjaus
    @Published var browserReady = false
    @Published var sessionId: String?
    @Published var prompts: [GuiPromptTemplate] = []
    @Published var overview: GuiOverviewResponse?
    @Published var statisticsRuns: [GuiStatisticsRun] = []
    @Published var selectedPromptByColumn: [String: String] = [:]
    @Published var selectedExerciseColumnKey: String?
    @Published var autopilotQueueColumnKeys: [String] = []
    @Published var draggedAutopilotColumnKey: String?
    @Published var autopilotResults: [GuiAutopilotQueueItemResult] = []
    @Published var autopilotRunning = false
    @Published var selectedLibraryPromptId: String?
    @Published var draftPromptId: String?
    @Published var draftPromptTitle = ""
    @Published var draftPromptBody = ""
    @Published var draftPromptModelProvider = "vertex_ai"
    @Published var draftPromptModelName = "gemini-3.1-pro-preview"
    @Published var draftPromptReasoningLevel = "medium"
    @Published var draftPromptBuiltIn = false
    @Published var promptSearchText = ""
    @Published var statusMessage = "Avaa selain vihreällä painikkeella. Kun siirryt kokeen yleisnäkymään, arvioitavat tehtävät tunnistetaan automaattisesti."
    @Published var resultMessage = "Yhtään tehtävää ei ole vielä arvioitu."
    @Published var isStartingBrowser = false
    @Published var isRefreshingOverview = false
    @Published var isAutoDetectingOverview = false
    @Published var gradingColumnKey: String?
    @Published var isStopGradingRequested = false
    @Published var isSavingPrompt = false
    @Published var isLoadingInitialState = false
    @Published var latestErrorMessage: String?
    @Published var statisticsErrorMessage: String?
    @Published var hideStudentNamesInGui = UserDefaults.standard.bool(forKey: GuiStore.hideStudentNamesDefaultsKey) {
        didSet {
            UserDefaults.standard.set(hideStudentNamesInGui, forKey: GuiStore.hideStudentNamesDefaultsKey)
        }
    }

    let promptPlaceholderHelp =
        "Tuetut paikkamerkit: (STUDENT), (PROGRESSION), (OBJECTIVE), (TARGET), (ANSWER), (MODELANSWER), (MAXPOINTS), (GROUP), (STUDENTS), (CATEGORY), (EXERCISE NUMBER). Vanhat paikkamerkit kuten (SWE PHRASE) ja (FIN ANSWER) toimivat edelleen."

    private let apiClient: GuiAPIClient
    private var overviewAutoDetectionTask: Task<Void, Never>?

    init(apiClient: GuiAPIClient = GuiAPIClient()) {
        self.apiClient = apiClient
    }

    var hasPrompts: Bool {
        !prompts.isEmpty
    }

    var filteredBuiltInPrompts: [GuiPromptTemplate] {
        filteredPrompts.filter(\.builtIn)
    }

    var filteredCustomPrompts: [GuiPromptTemplate] {
        filteredPrompts.filter { !$0.builtIn }
    }

    var selectedPromptFromLibrary: GuiPromptTemplate? {
        prompts.first(where: { $0.promptId == selectedLibraryPromptId })
    }

    var canSavePrompt: Bool {
        !draftPromptTitle.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && !draftPromptBody.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    var editorModeText: String {
        if draftPromptId == nil {
            return "Valitse kirjastosta kriteeri tai luo uusi kriteeri. Valitun promptin sisältöä voi muokata suoraan napsauttamalla sitä vasemmalta."
        }
        if draftPromptBuiltIn {
            return "Oletuskriteeri. Kun tallennat muutokset, tämä oletusversio päivittyy kirjastoon säilyttäen saman tunnisteen."
        }
        return "Mukautettu kriteeri. Klikkaa kirjastosta promptia, muokkaa ja tallenna."
    }

    var welcomeTitle: String {
        "Tervetuloa, User"
    }

    var displayModeSummary: String {
        hideStudentNamesInGui ? "Opiskelijoiden nimet piilotetaan käyttöliittymästä." : "Opiskelijoiden nimet näkyvät käyttöliittymässä."
    }

    var displayedStatusMessage: String {
        redactedTextForDisplay(statusMessage)
    }

    var displayedResultMessage: String {
        redactedTextForDisplay(resultMessage)
    }

    var detectedExerciseCount: Int {
        overview?.exercises.count ?? 0
    }

    var statisticsRunCount: Int {
        statisticsRuns.count
    }

    var autopilotQueueExercises: [GuiExerciseColumn] {
        let exerciseMap = Dictionary(uniqueKeysWithValues: (overview?.exercises ?? []).map { ($0.columnKey, $0) })
        return autopilotQueueColumnKeys.compactMap { exerciseMap[$0] }
    }

    var availableAutopilotExercises: [GuiExerciseColumn] {
        let queuedKeys = Set(autopilotQueueColumnKeys)
        return (overview?.exercises ?? []).filter { !queuedKeys.contains($0.columnKey) }
    }

    var statisticsEntryCount: Int {
        statisticsRuns.reduce(0) { partialResult, run in
            partialResult + run.entries.count
        }
    }

    var logEntryCount: Int {
        statisticsEntryCount
    }

    func loadInitialData() async {
        isLoadingInitialState = true
        defer { isLoadingInitialState = false }

        var criticalLoadErrors: [String] = []
        statisticsErrorMessage = nil

        do {
            let resolvedState = try await apiClient.state()
            browserReady = resolvedState.browserReady
            sessionId = resolvedState.sessionId
            if browserReady {
                statusMessage = "Selain on jo käynnissä. Siirry Sanoman kokeen yleisnäkymään, niin tehtävät tunnistetaan automaattisesti."
            }
        } catch {
            criticalLoadErrors.append(error.localizedDescription)
        }

        do {
            let resolvedPrompts = try await apiClient.prompts()
            prompts = resolvedPrompts
            syncDraftSelection()
        } catch {
            criticalLoadErrors.append(error.localizedDescription)
        }

        do {
            let resolvedStatistics = try await apiClient.statistics()
            statisticsRuns = resolvedStatistics.runs
        } catch {
            statisticsErrorMessage = error.localizedDescription
        }

        if !criticalLoadErrors.isEmpty {
            latestErrorMessage = criticalLoadErrors.joined(separator: " | ")
            if prompts.isEmpty {
                statusMessage = "Paikalliseen GUI-palvelimeen ei saatu yhteyttä."
            }
        } else {
            latestErrorMessage = nil
        }

        updateAutomaticOverviewDetection()
    }

    func visibleStudentName(_ rawName: String) -> String {
        let trimmedName = rawName.trimmingCharacters(in: .whitespacesAndNewlines)
        let fallback = trimmedName.isEmpty ? "Tuntematon opiskelija" : trimmedName
        guard hideStudentNamesInGui else { return fallback }
        guard !trimmedName.isEmpty else { return "Piilotettu opiskelija" }

        var accumulator = 5381
        for scalar in trimmedName.unicodeScalars {
            accumulator = ((accumulator << 5) &+ accumulator) &+ Int(scalar.value)
        }
        let stableCode = abs(accumulator % 10_000)
        return String(format: "Opiskelija %04d", stableCode)
    }

    func redactedTextForDisplay(_ rawText: String) -> String {
        guard hideStudentNamesInGui else { return rawText }
        var redacted = rawText
        for name in knownStudentNames.sorted(by: { $0.count > $1.count }) {
            redacted = redacted.replacingOccurrences(of: name, with: visibleStudentName(name))
        }
        return redacted
    }

    private var knownStudentNames: Set<String> {
        var names = Set<String>()
        for run in statisticsRuns {
            for entry in run.entries {
                let trimmed = entry.studentName.trimmingCharacters(in: .whitespacesAndNewlines)
                if !trimmed.isEmpty {
                    names.insert(trimmed)
                }
            }
        }
        if let overview {
            for observed in overview.observedScores {
                let trimmed = observed.studentName.trimmingCharacters(in: .whitespacesAndNewlines)
                if !trimmed.isEmpty {
                    names.insert(trimmed)
                }
            }
        }
        return names
    }

    func startBrowser() async {
        guard !isStartingBrowser else { return }
        isStartingBrowser = true
        latestErrorMessage = nil
        statusMessage = "Käynnistetään GradeAgent-selain..."
        defer { isStartingBrowser = false }

        do {
            let response = try await apiClient.startBrowser()
            browserReady = response.browserReady
            sessionId = response.sessionId
            overview = nil
            selectedPromptByColumn = [:]
            selectedExerciseColumnKey = nil
            autopilotQueueColumnKeys = []
            autopilotResults = []
            isStopGradingRequested = false
            statusMessage = "Selain on auki. Siirry Sanoman kokeen yleisnäkymään, niin tehtävät ilmestyvät tähän automaattisesti."
            resultMessage = "Selaimen istunto on valmis: \(response.sessionId)"
            updateAutomaticOverviewDetection()
        } catch {
            latestErrorMessage = error.localizedDescription
            statusMessage = "Selaimen käynnistäminen epäonnistui."
        }
    }

    func refreshOverview() async {
        guard browserReady else { return }
        guard !isRefreshingOverview else { return }
        isRefreshingOverview = true
        latestErrorMessage = nil
        statusMessage = "Luetaan yleisnäkymän DOM-rakenne ja kerätään arvioimattomat tehtävät..."
        defer { isRefreshingOverview = false }

        do {
            await ensurePromptsLoadedIfNeeded()
            let response = try await apiClient.overview()
            applyOverviewResponse(response, source: .manual)
        } catch {
            latestErrorMessage = error.localizedDescription
            statusMessage = "Yleisnäkymää ei voitu lukea."
        }
    }

    func stopBrowser() async {
        latestErrorMessage = nil
        do {
            let response = try await apiClient.stopBrowser()
            browserReady = response.browserReady
            sessionId = response.sessionId
            overview = nil
            selectedPromptByColumn = [:]
            selectedExerciseColumnKey = nil
            autopilotQueueColumnKeys = []
            autopilotResults = []
            autopilotRunning = false
            draggedAutopilotColumnKey = nil
            isStopGradingRequested = false
            isAutoDetectingOverview = false
            overviewAutoDetectionTask?.cancel()
            overviewAutoDetectionTask = nil
            statusMessage = "Selain pysäytettiin. Voit käynnistää uuden istunnon vihreästä painikkeesta."
            resultMessage = "Selainistunto suljettiin hallitusti."
        } catch {
            latestErrorMessage = error.localizedDescription
            statusMessage = "Selaimen pysäyttäminen epäonnistui."
        }
    }

    func gradeExercise(_ exercise: GuiExerciseColumn) async {
        guard await reloadPrompts() else {
            statusMessage = "Kriteerejä ei voitu päivittää ennen arvioinnin aloitusta."
            return
        }
        guard gradingColumnKey == nil else { return }
        if selectedExerciseColumnKey != exercise.columnKey {
            selectExercise(exercise)
        }
        guard let prompt = selectedPrompt(for: exercise) else {
            latestErrorMessage = "Valitse tehtävälle kriteeri ennen arvioinnin käynnistystä."
            return
        }

        gradingColumnKey = exercise.columnKey
        isStopGradingRequested = false
        latestErrorMessage = nil
        statusMessage = "Arvioidaan tehtävää '\(exercise.title)' kriteerillä '\(prompt.title)'..."
        defer {
            gradingColumnKey = nil
            isStopGradingRequested = false
        }

        do {
            let response = try await apiClient.gradeExercise(
                GuiGradeExerciseRequest(
                    columnKey: exercise.columnKey,
                    instructions: prompt.body,
                    promptId: prompt.promptId,
                    promptTitle: prompt.title,
                    modelProvider: prompt.modelProvider,
                    modelName: prompt.modelName,
                    reasoningLevel: prompt.reasoningLevel,
                    maxSteps: 260
                )
            )
            overview = GuiOverviewResponse(
                assignmentTitle: overview?.assignmentTitle ?? "",
                groupName: overview?.groupName,
                studentsAnsweredCount: overview?.studentsAnsweredCount,
                studentsTotalCount: overview?.studentsTotalCount,
                exercises: response.exercises,
                observedScores: overview?.observedScores ?? []
            )
            syncExercisePromptSelections()
            syncAutopilotQueueWithOverview()
            selectedExerciseColumnKey = nil
            await refreshStatistics()
            statusMessage = isStopGradingRequested
                ? "Arviointi pysäytettiin hallitusti. Selain on yhä auki seuraavaa valintaa varten."
                : "Selain on yhä auki. Valitse seuraava tehtävä, kun haluat jatkaa."
            let reportPart = response.result.reportPath.map { " Raportti: \($0)" } ?? ""
            resultMessage = response.result.summary + reportPart
        } catch {
            latestErrorMessage = error.localizedDescription
            statusMessage = isStopGradingRequested ? "Arvioinnin pysäytyspyyntö epäonnistui." : "Tehtävän arviointi epäonnistui."
        }
    }

    func stopCurrentGrading() async {
        guard gradingColumnKey != nil || autopilotRunning else { return }
        guard !isStopGradingRequested else { return }
        latestErrorMessage = nil
        isStopGradingRequested = true
        statusMessage = "Pysäytyspyyntö lähetetty. Nykyinen arviointivaihe päätetään hallitusti ennen pysähtymistä."

        do {
            try await apiClient.stopGrading()
        } catch {
            isStopGradingRequested = false
            latestErrorMessage = error.localizedDescription
            statusMessage = "Arvioinnin pysäytyspyyntö epäonnistui."
        }
    }

    func enqueueAutopilotExercise(_ exercise: GuiExerciseColumn) {
        guard !autopilotQueueColumnKeys.contains(exercise.columnKey) else { return }
        autopilotQueueColumnKeys.append(exercise.columnKey)
        latestErrorMessage = nil
    }

    func removeAutopilotExercise(_ columnKey: String) {
        autopilotQueueColumnKeys.removeAll { $0 == columnKey }
        if draggedAutopilotColumnKey == columnKey {
            draggedAutopilotColumnKey = nil
        }
    }

    func moveAutopilotExercise(_ columnKey: String, before targetColumnKey: String) {
        guard columnKey != targetColumnKey else { return }
        guard let fromIndex = autopilotQueueColumnKeys.firstIndex(of: columnKey),
              let targetIndex = autopilotQueueColumnKeys.firstIndex(of: targetColumnKey) else {
            return
        }
        let item = autopilotQueueColumnKeys.remove(at: fromIndex)
        let adjustedIndex = fromIndex < targetIndex ? max(targetIndex - 1, 0) : targetIndex
        autopilotQueueColumnKeys.insert(item, at: adjustedIndex)
    }

    func startAutopilot() async {
        guard await reloadPrompts() else {
            statusMessage = "Kriteerejä ei voitu päivittää ennen Autopilotin aloitusta."
            return
        }
        guard gradingColumnKey == nil, !autopilotRunning else { return }
        let queuedExercises = autopilotQueueExercises
        guard !queuedExercises.isEmpty else {
            latestErrorMessage = "Lisää Autopilotiin ainakin yksi tehtävä ennen aloitusta."
            return
        }

        var items: [GuiAutopilotQueueItemRequest] = []
        for exercise in queuedExercises {
            guard let prompt = selectedPrompt(for: exercise) else {
                latestErrorMessage = "Valitse kaikille Autopilotin tehtäville kriteeri ennen aloitusta."
                return
            }
            items.append(
                GuiAutopilotQueueItemRequest(
                    columnKey: exercise.columnKey,
                    instructions: prompt.body,
                    promptId: prompt.promptId,
                    promptTitle: prompt.title,
                    modelProvider: prompt.modelProvider,
                    modelName: prompt.modelName,
                    reasoningLevel: prompt.reasoningLevel,
                    maxSteps: 260
                )
            )
        }

        autopilotRunning = true
        isStopGradingRequested = false
        latestErrorMessage = nil
        statusMessage = "Autopilot aloittaa \(queuedExercises.count) tehtävän arvioinnin määritetyssä järjestyksessä..."
        defer {
            autopilotRunning = false
            isStopGradingRequested = false
            gradingColumnKey = nil
            draggedAutopilotColumnKey = nil
        }

        do {
            let response = try await apiClient.runAutopilot(GuiAutopilotRunRequest(items: items))
            autopilotResults = response.items
            overview = GuiOverviewResponse(
                assignmentTitle: overview?.assignmentTitle ?? "",
                groupName: overview?.groupName,
                studentsAnsweredCount: overview?.studentsAnsweredCount,
                studentsTotalCount: overview?.studentsTotalCount,
                exercises: response.exercises,
                observedScores: overview?.observedScores ?? []
            )
            syncExercisePromptSelections()
            syncAutopilotQueueWithOverview()
            await refreshStatistics()
            statusMessage = isStopGradingRequested
                ? "Autopilot pysäytettiin hallitusti. Selain on yhä auki."
                : "Autopilot suoritettiin loppuun. Selain on yhä auki seuraavaa ajoa varten."
            resultMessage = response.summary
        } catch {
            latestErrorMessage = error.localizedDescription
            statusMessage = isStopGradingRequested
                ? "Autopilotin pysäytyspyyntö epäonnistui."
                : "Autopilotin suoritus epäonnistui."
        }
    }

    func refreshStatistics() async {
        do {
            let response = try await apiClient.statistics()
            statisticsRuns = response.runs
            statisticsErrorMessage = nil
        } catch {
            statisticsErrorMessage = error.localizedDescription
        }
    }

    func ensurePromptsLoadedIfNeeded() async {
        guard prompts.isEmpty else { return }
        _ = await reloadPrompts()
    }

    @discardableResult
    func reloadPrompts() async -> Bool {
        do {
            let resolvedPrompts = try await apiClient.prompts()
            prompts = resolvedPrompts
            syncDraftSelection()
            syncExercisePromptSelections()
            return true
        } catch {
            latestErrorMessage = error.localizedDescription
            return false
        }
    }

    private func updateAutomaticOverviewDetection() {
        overviewAutoDetectionTask?.cancel()
        overviewAutoDetectionTask = nil

        guard browserReady else {
            isAutoDetectingOverview = false
            return
        }

        isAutoDetectingOverview = true
        overviewAutoDetectionTask = Task { [weak self] in
            guard let self else { return }
            while !Task.isCancelled {
                await self.performAutomaticOverviewDetectionTick()
                try? await Task.sleep(for: .seconds(2))
            }
        }
    }

    private func performAutomaticOverviewDetectionTick() async {
        guard browserReady else { return }
        guard gradingColumnKey == nil else { return }
        guard !isRefreshingOverview else { return }

        do {
            await ensurePromptsLoadedIfNeeded()
            let response = try await apiClient.overview()
            applyOverviewResponse(response, source: .automatic)
            latestErrorMessage = nil
        } catch {
            if let resolvedState = try? await apiClient.state() {
                browserReady = resolvedState.browserReady
                sessionId = resolvedState.sessionId
                if !resolvedState.browserReady {
                    overview = nil
                    selectedPromptByColumn = [:]
                    selectedExerciseColumnKey = nil
                    autopilotQueueColumnKeys = []
                    autopilotResults = []
                    autopilotRunning = false
                    draggedAutopilotColumnKey = nil
                    isAutoDetectingOverview = false
                    overviewAutoDetectionTask?.cancel()
                    overviewAutoDetectionTask = nil
                    latestErrorMessage = nil
                    statusMessage = "Selainyhteys katkesi. Käynnistä selain uudelleen vihreästä painikkeesta."
                    resultMessage = "Edellinen selainistunto ei ole enää käytettävissä."
                    return
                }
            }
            if overview == nil {
                statusMessage = "Selain on auki. Siirry Sanoman kokeen yleisnäkymään, niin tehtävät ilmestyvät tähän automaattisesti."
            }
        }
    }

    private enum OverviewUpdateSource {
        case manual
        case automatic
    }

    private func applyOverviewResponse(_ response: GuiOverviewResponse, source: OverviewUpdateSource) {
        let previousExerciseKeys = Set(overview?.exercises.map(\.columnKey) ?? [])
        let nextExerciseKeys = Set(response.exercises.map(\.columnKey))
        let changed = previousExerciseKeys != nextExerciseKeys || overview?.groupName != response.groupName

        overview = response
        syncExercisePromptSelections()
        syncAutopilotQueueWithOverview()

        if response.exercises.isEmpty {
            statusMessage = "Kokeen yleisnäkymä havaittiin, mutta arvioimattomia tehtäviä ei löytynyt."
            if source == .manual {
                resultMessage = "Jos tämä näyttää väärältä, varmista että olet kokeen yleisnäkymässä. Tunnistus päivittyy automaattisesti."
            }
            return
        }

        if changed || source == .manual {
            statusMessage = "Löytyi \(response.exercises.count) arvioimatonta tehtävää. Valitse jokaiselle kriteeri ja aloita arviointi."
            resultMessage = "Selain pysyy auki jokaisen arvioinnin jälkeen. Valitse seuraava tehtävä, kun haluat jatkaa."
        }
    }

    func createPrompt() async {
        latestErrorMessage = nil
        do {
            let prompt = try await apiClient.newPrompt()
            prompts.append(prompt)
            prompts.sort { $0.title.localizedCaseInsensitiveCompare($1.title) == .orderedAscending }
            selectLibraryPrompt(prompt.promptId)
            selectedPage = .kriteerit
            statusMessage = "Uusi kriteeri avattiin muokattavaksi."
        } catch {
            latestErrorMessage = error.localizedDescription
            statusMessage = "Uuden kriteerin luonti epäonnistui."
        }
    }

    func saveCurrentPrompt() async {
        guard !isSavingPrompt else { return }
        isSavingPrompt = true
        latestErrorMessage = nil
        defer { isSavingPrompt = false }

        do {
            let savedPrompt = try await apiClient.savePrompt(
                GuiPromptSaveRequest(
                    promptId: draftPromptId,
                    title: draftPromptTitle,
                    body: draftPromptBody,
                    modelProvider: draftPromptModelProvider,
                    modelName: draftPromptModelName,
                    reasoningLevel: draftPromptReasoningLevel
                )
            )
            if let index = prompts.firstIndex(where: { $0.promptId == savedPrompt.promptId }) {
                prompts[index] = savedPrompt
            } else {
                prompts.append(savedPrompt)
            }
            prompts.sort { $0.title.localizedCaseInsensitiveCompare($1.title) == .orderedAscending }
            selectLibraryPrompt(savedPrompt.promptId)
            syncExercisePromptSelections()
            statusMessage = "Kriteeri '\(savedPrompt.title)' tallennettiin kirjastoon."
            resultMessage = "Kirjaston kriteerit ovat nyt käytettävissä Ohjaus-sivulla."
        } catch {
            latestErrorMessage = error.localizedDescription
            statusMessage = "Kriteerin tallennus epäonnistui."
        }
    }

    func selectLibraryPrompt(_ promptId: String?) {
        selectedLibraryPromptId = promptId
        guard let prompt = prompts.first(where: { $0.promptId == promptId }) else {
            draftPromptId = nil
            draftPromptTitle = ""
            draftPromptBody = ""
            draftPromptModelProvider = "vertex_ai"
            draftPromptModelName = "gemini-3.1-pro-preview"
            draftPromptReasoningLevel = "medium"
            draftPromptBuiltIn = false
            return
        }
        draftPromptId = prompt.promptId
        draftPromptTitle = prompt.title
        draftPromptBody = prompt.body
        draftPromptModelProvider = prompt.modelProvider
        draftPromptModelName = prompt.modelName
        draftPromptReasoningLevel = prompt.reasoningLevel
        draftPromptBuiltIn = prompt.builtIn
    }

    func setPrompt(_ promptId: String, for columnKey: String) {
        selectedPromptByColumn[columnKey] = promptId
    }

    func selectExercise(_ exercise: GuiExerciseColumn) {
        selectedExerciseColumnKey = exercise.columnKey
        latestErrorMessage = nil
    }

    func selectedPrompt(for exercise: GuiExerciseColumn) -> GuiPromptTemplate? {
        let selectedId = selectedPromptByColumn[exercise.columnKey]
        return prompts.first(where: { $0.promptId == selectedId }) ?? prompts.first
    }

    func isGrading(_ exercise: GuiExerciseColumn) -> Bool {
        gradingColumnKey == exercise.columnKey
    }

    func isSelected(_ exercise: GuiExerciseColumn) -> Bool {
        selectedExerciseColumnKey == exercise.columnKey
    }

    func shutdown() async {
        overviewAutoDetectionTask?.cancel()
        overviewAutoDetectionTask = nil
        isAutoDetectingOverview = false
        await apiClient.shutdown()
    }

    private func syncDraftSelection() {
        if let selectedLibraryPromptId,
           prompts.contains(where: { $0.promptId == selectedLibraryPromptId }) {
            selectLibraryPrompt(selectedLibraryPromptId)
            return
        }
        selectLibraryPrompt(prompts.first?.promptId)
    }

    private func syncExercisePromptSelections() {
        let validPromptIds = Set(prompts.map(\.promptId))
        var updatedSelection: [String: String] = [:]
        for exercise in overview?.exercises ?? [] {
            if let current = selectedPromptByColumn[exercise.columnKey], validPromptIds.contains(current) {
                updatedSelection[exercise.columnKey] = current
            } else if let firstPrompt = prompts.first {
                updatedSelection[exercise.columnKey] = firstPrompt.promptId
            }
        }
        selectedPromptByColumn = updatedSelection
        if let selectedExerciseColumnKey, updatedSelection[selectedExerciseColumnKey] == nil {
            self.selectedExerciseColumnKey = nil
        }
    }

    private func syncAutopilotQueueWithOverview() {
        let validKeys = Set(overview?.exercises.map(\.columnKey) ?? [])
        autopilotQueueColumnKeys.removeAll { !validKeys.contains($0) }
        if let draggedAutopilotColumnKey, !validKeys.contains(draggedAutopilotColumnKey) {
            self.draggedAutopilotColumnKey = nil
        }
    }

    private var filteredPrompts: [GuiPromptTemplate] {
        let trimmedQuery = promptSearchText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedQuery.isEmpty else {
            return prompts
        }
        return prompts.filter { prompt in
            prompt.title.localizedCaseInsensitiveContains(trimmedQuery)
                || prompt.body.localizedCaseInsensitiveContains(trimmedQuery)
        }
    }
}
