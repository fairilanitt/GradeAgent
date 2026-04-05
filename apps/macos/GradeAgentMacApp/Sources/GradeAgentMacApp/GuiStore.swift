import Foundation
import SwiftUI

enum AppPage: String, CaseIterable, Identifiable {
    case ohjaus
    case kriteerit
    case tilastot

    var id: String { rawValue }

    var title: String {
        switch self {
        case .ohjaus:
            return "Ohjaus"
        case .kriteerit:
            return "Kriteerit"
        case .tilastot:
            return "Tilastot"
        }
    }

    var systemImage: String {
        switch self {
        case .ohjaus:
            return "slider.horizontal.3"
        case .kriteerit:
            return "books.vertical"
        case .tilastot:
            return "chart.xyaxis.line"
        }
    }
}

@MainActor
final class GuiStore: ObservableObject {
    @Published var selectedPage: AppPage = .ohjaus
    @Published var browserReady = false
    @Published var sessionId: String?
    @Published var prompts: [GuiPromptTemplate] = []
    @Published var overview: GuiOverviewResponse?
    @Published var statisticsRuns: [GuiStatisticsRun] = []
    @Published var selectedPromptByColumn: [String: String] = [:]
    @Published var selectedLibraryPromptId: String?
    @Published var draftPromptId: String?
    @Published var draftPromptTitle = ""
    @Published var draftPromptBody = ""
    @Published var draftPromptBuiltIn = false
    @Published var promptSearchText = ""
    @Published var statusMessage = "Avaa selain vihreällä painikkeella. Kun siirryt Sanoman kokeen yleisnäkymään, arvioitavat tehtävät tunnistetaan automaattisesti."
    @Published var resultMessage = "Yhtään tehtävää ei ole vielä arvioitu."
    @Published var isStartingBrowser = false
    @Published var isRefreshingOverview = false
    @Published var isAutoDetectingOverview = false
    @Published var gradingColumnKey: String?
    @Published var isSavingPrompt = false
    @Published var isLoadingInitialState = false
    @Published var latestErrorMessage: String?

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

    var detectedExerciseCount: Int {
        overview?.exercises.count ?? 0
    }

    var statisticsRunCount: Int {
        statisticsRuns.count
    }

    var statisticsEntryCount: Int {
        statisticsRuns.reduce(0) { partialResult, run in
            partialResult + run.entries.count
        }
    }

    func loadInitialData() async {
        isLoadingInitialState = true
        defer { isLoadingInitialState = false }

        var loadErrors: [String] = []

        do {
            let resolvedState = try await apiClient.state()
            browserReady = resolvedState.browserReady
            sessionId = resolvedState.sessionId
            if browserReady {
                statusMessage = "Selain on jo käynnissä. Siirry Sanoman kokeen yleisnäkymään, niin tehtävät tunnistetaan automaattisesti."
            }
        } catch {
            loadErrors.append(error.localizedDescription)
        }

        do {
            let resolvedPrompts = try await apiClient.prompts()
            prompts = resolvedPrompts
            syncDraftSelection()
        } catch {
            loadErrors.append(error.localizedDescription)
        }

        do {
            let resolvedStatistics = try await apiClient.statistics()
            statisticsRuns = resolvedStatistics.runs
        } catch {
            loadErrors.append(error.localizedDescription)
        }

        if !loadErrors.isEmpty {
            latestErrorMessage = loadErrors.joined(separator: " | ")
            if prompts.isEmpty {
                statusMessage = "Paikalliseen GUI-palvelimeen ei saatu yhteyttä."
            }
        }

        updateAutomaticOverviewDetection()
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
            statusMessage = "Sanoman yleisnäkymää ei voitu lukea."
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
        await ensurePromptsLoadedIfNeeded()
        guard gradingColumnKey == nil else { return }
        guard let prompt = selectedPrompt(for: exercise) else {
            latestErrorMessage = "Valitse tehtävälle kriteeri ennen arvioinnin käynnistystä."
            return
        }

        gradingColumnKey = exercise.columnKey
        latestErrorMessage = nil
        statusMessage = "Arvioidaan tehtävää '\(exercise.title)' kriteerillä '\(prompt.title)'..."
        defer { gradingColumnKey = nil }

        do {
            let response = try await apiClient.gradeExercise(
                GuiGradeExerciseRequest(
                    columnKey: exercise.columnKey,
                    instructions: prompt.body,
                    promptId: prompt.promptId,
                    promptTitle: prompt.title,
                    maxSteps: 260
                )
            )
            overview = GuiOverviewResponse(
                assignmentTitle: overview?.assignmentTitle ?? "",
                groupName: overview?.groupName,
                studentsAnsweredCount: overview?.studentsAnsweredCount,
                studentsTotalCount: overview?.studentsTotalCount,
                exercises: response.exercises
            )
            syncExercisePromptSelections()
            if let refreshedStatistics = try? await apiClient.statistics() {
                statisticsRuns = refreshedStatistics.runs
            }
            statusMessage = "Selain on yhä auki. Valitse seuraava tehtävä, kun haluat jatkaa."
            let reportPart = response.result.reportPath.map { " Raportti: \($0)" } ?? ""
            resultMessage = response.result.summary + reportPart
        } catch {
            latestErrorMessage = error.localizedDescription
            statusMessage = "Tehtävän arviointi epäonnistui."
        }
    }

    func refreshStatistics() async {
        do {
            let response = try await apiClient.statistics()
            statisticsRuns = response.runs
        } catch {
            latestErrorMessage = error.localizedDescription
        }
    }

    func ensurePromptsLoadedIfNeeded() async {
        guard prompts.isEmpty else { return }
        do {
            let resolvedPrompts = try await apiClient.prompts()
            prompts = resolvedPrompts
            syncDraftSelection()
            syncExercisePromptSelections()
        } catch {
            latestErrorMessage = error.localizedDescription
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
                    body: draftPromptBody
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
            draftPromptBuiltIn = false
            return
        }
        draftPromptId = prompt.promptId
        draftPromptTitle = prompt.title
        draftPromptBody = prompt.body
        draftPromptBuiltIn = prompt.builtIn
    }

    func setPrompt(_ promptId: String, for columnKey: String) {
        selectedPromptByColumn[columnKey] = promptId
    }

    func selectedPrompt(for exercise: GuiExerciseColumn) -> GuiPromptTemplate? {
        let selectedId = selectedPromptByColumn[exercise.columnKey]
        return prompts.first(where: { $0.promptId == selectedId }) ?? prompts.first
    }

    func isGrading(_ exercise: GuiExerciseColumn) -> Bool {
        gradingColumnKey == exercise.columnKey
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
