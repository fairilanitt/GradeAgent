import AppKit
import SwiftUI
import UniformTypeIdentifiers

@main
struct GradeAgentMacApp: App {
    @NSApplicationDelegateAdaptor(GradeAgentAppDelegate.self) private var appDelegate
    @StateObject private var store = GuiStore()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(store)
                .frame(minWidth: 920, minHeight: 640)
                .task {
                    await store.loadInitialData()
                }
        }
        .defaultSize(width: 1360, height: 880)
        .windowResizability(.contentMinSize)
        .windowStyle(.hiddenTitleBar)
    }
}

final class GradeAgentAppDelegate: NSObject, NSApplicationDelegate {
    func applicationShouldTerminateAfterLastWindowClosed(_: NSApplication) -> Bool {
        true
    }

    func applicationWillTerminate(_: Notification) {
        GuiAPIClient.shutdownSynchronously()
    }
}

struct RootView: View {
    @EnvironmentObject private var store: GuiStore

    var body: some View {
        GeometryReader { proxy in
            let windowWidth = proxy.size.width
            let heroHeight = min(210.0, max(138.0, proxy.size.height * 0.22))
            let compactWindow = windowWidth < 1180
            let sidebarWidth = compactWindow ? 178.0 : 192.0

            ZStack(alignment: .top) {
                LiquidGlassBackground()

                HeroImageOverlayView()
                    .frame(height: heroHeight)
                    .frame(maxWidth: .infinity)
                    .ignoresSafeArea(edges: .top)

                WorkspaceShell {
                    HStack(alignment: .top, spacing: compactWindow ? 14 : 20) {
                        SidebarView(compact: compactWindow)
                            .frame(width: sidebarWidth)
                            .frame(maxHeight: .infinity)

                        VStack(alignment: .leading, spacing: compactWindow ? 14 : 18) {
                            if store.selectedPage == .ohjaus {
                                HeroDashboardView(compact: compactWindow)
                            }
                            Group {
                                switch store.selectedPage {
                                case .ohjaus:
                                    ControlPageView(compact: compactWindow)
                                case .autopilot:
                                    AutopilotPageView(compact: compactWindow)
                                case .arviointikirja:
                                    GradebookPageView(compact: compactWindow)
                                case .kriteerit:
                                    CriteriaPageView(compact: compactWindow)
                                case .tilastot:
                                    StatisticsPageView(compact: compactWindow)
                                case .lokit:
                                    LogsPageView(compact: compactWindow)
                                case .asetukset:
                                    SettingsPageView(compact: compactWindow)
                                }
                            }
                            .frame(maxWidth: .infinity, maxHeight: .infinity)
                        }
                        .padding(.top, store.selectedPage == .ohjaus ? 6 : 0)
                        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
                    }
                    .padding(.horizontal, compactWindow ? 14 : 18)
                    .padding(.vertical, compactWindow ? 14 : 18)
                }
                .padding(.leading, compactWindow ? 2 : 6)
                .padding(.trailing, compactWindow ? 16 : 24)
                .padding(.bottom, compactWindow ? 16 : 24)
                .padding(.top, compactWindow ? 6 : 8)
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            }
        }
    }
}

struct SidebarView: View {
    @EnvironmentObject private var store: GuiStore
    let compact: Bool
    private let workspacePages: [AppPage] = [.ohjaus, .autopilot, .arviointikirja, .kriteerit]
    private let insightPages: [AppPage] = [.tilastot, .lokit, .asetukset]

    var body: some View {
        SidebarPanel {
            VStack(alignment: .leading, spacing: compact ? 24 : 28) {
                    VStack(alignment: .leading, spacing: compact ? 14 : 18) {
                        SidebarGlyph()

                        VStack(alignment: .leading, spacing: 6) {
                            Text("Arviointi")
                                .font(.system(size: compact ? 23 : 25, weight: .bold, design: .rounded))
                                .foregroundStyle(.white.opacity(0.96))

                            Text(store.browserReady ? "Selain on valmis ja tehtävät päivittyvät automaattisesti." : "Käynnistä selain ja siirry kokeen yleisnäkymään.")
                                .font(.system(size: compact ? 10 : 11, weight: .medium, design: .rounded))
                                .foregroundStyle(.white.opacity(0.58))
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }

                SidebarNavigationSection(title: "Työtila") {
                    VStack(alignment: .leading, spacing: compact ? 6 : 8) {
                        ForEach(workspacePages) { page in
                            SidebarButton(
                                title: page.title,
                                systemImage: page.systemImage,
                                selected: store.selectedPage == page
                            ) {
                                store.selectedPage = page
                            }
                        }
                    }
                }

                Divider()
                    .overlay(Color.white.opacity(0.14))

                SidebarNavigationSection(title: "Seuranta") {
                    VStack(alignment: .leading, spacing: compact ? 6 : 8) {
                        ForEach(insightPages) { page in
                            SidebarButton(
                                title: page.title,
                                systemImage: page.systemImage,
                                selected: store.selectedPage == page
                            ) {
                                store.selectedPage = page
                            }
                        }
                    }
                }

                Spacer(minLength: 0)
            }
            .padding(.horizontal, compact ? 16 : 20)
            .padding(.vertical, compact ? 18 : 22)
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        }
    }
}

struct ControlPageView: View {
    @EnvironmentObject private var store: GuiStore
    let compact: Bool

    var body: some View {
        IntegratedPageSurface {
            VStack(alignment: .leading, spacing: 16) {
                VStack(alignment: .leading, spacing: 12) {
                    HStack(alignment: .firstTextBaseline) {
                        VStack(alignment: .leading, spacing: 6) {
                            Text("Havaitut tehtävät")
                                .font(.system(size: 20, weight: .bold, design: .rounded))
                                .foregroundStyle(.white)
                            Text("Tämä alareunan työtila näkyy vain Ohjaus-sivulla. Täältä valitaan löydetyt tehtäväsarjat arviointiin.")
                                .font(.system(size: 13, weight: .medium, design: .rounded))
                                .foregroundStyle(.white.opacity(0.76))
                        }
                        Spacer(minLength: 0)
                        if let exerciseCount = store.overview?.exercises.count {
                            Text("\(exerciseCount) tehtävää")
                                .font(.system(size: 12, weight: .bold, design: .rounded))
                                .foregroundStyle(.white.opacity(0.74))
                        }
                    }

                    AdaptiveAxisStack(horizontal: !compact, spacing: 10) {
                        if let overview = store.overview {
                            MiniInfoPill(label: "Koe", value: overview.assignmentTitle)
                            MiniInfoPill(label: "Ryhmä", value: overview.groupName ?? "-")
                            if let answered = overview.studentsAnsweredCount,
                               let total = overview.studentsTotalCount {
                                MiniInfoPill(label: "Oppilaat", value: "\(answered) / \(total)")
                            }
                        }
                        MiniInfoPill(
                            label: "Tunnistus",
                            value: store.browserReady
                                ? (store.isAutoDetectingOverview ? "Automaattinen haku päällä" : "Odottaa yleisnäkymää")
                                : "Selain ei ole auki"
                        )
                        MiniInfoPill(
                            label: "Tila",
                            value: store.latestErrorMessage.map(store.redactedTextForDisplay) ?? store.displayedResultMessage
                        )
                    }

                    Divider()
                        .overlay(Color.white.opacity(0.14))
                }

                if let exercises = store.overview?.exercises, !exercises.isEmpty {
                    ScrollView {
                        LazyVGrid(
                            columns: [
                                GridItem(.adaptive(minimum: compact ? 220 : 250, maximum: compact ? 250 : 290), spacing: 14, alignment: .top)
                            ],
                            alignment: .leading,
                            spacing: 14
                        ) {
                            ForEach(exercises) { exercise in
                                ExerciseCardView(exercise: exercise)
                                    .frame(maxWidth: .infinity, minHeight: compact ? 250 : 276, alignment: .topLeading)
                            }
                        }
                        .padding(.bottom, 6)
                    }
                    .scrollIndicators(.hidden)
                } else {
                    EmptyStateView(
                        title: "Ei havaittuja tehtäviä",
                        message: "Kun selain on käynnissä ja avaat Sanoman kokeen yleisnäkymän, arvioimattomat tehtävät ilmestyvät tähän automaattisesti."
                    )
                    .frame(maxHeight: .infinity)
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        }
    }
}

struct ExerciseCardView: View {
    @EnvironmentObject private var store: GuiStore
    let exercise: GuiExerciseColumn

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .top, spacing: 10) {
                VStack(alignment: .leading, spacing: 6) {
                    Text(exercise.title)
                        .font(.system(size: 17, weight: .bold, design: .rounded))
                        .foregroundStyle(.white)
                        .lineLimit(2)

                    if let categoryName = exercise.categoryName {
                        PromptTag(title: categoryName)
                    }
                }

                Spacer(minLength: 0)

                PromptTag(title: store.isSelected(exercise) ? "Valittu" : "Valitse")
            }

            VStack(alignment: .leading, spacing: 8) {
                ExerciseInfoLine(label: "Tehtävänumero", value: exercise.exerciseNumber ?? "-")
                ExerciseInfoLine(label: "Arvioimatta", value: "\(exercise.pendingCellCount) / \(exercise.totalCellCount)")
                ExerciseInfoLine(label: "Valmiina", value: "\(exercise.reviewedCellCount) / \(exercise.totalCellCount)")
            }

            VStack(alignment: .leading, spacing: 8) {
                Text("Kriteeri")
                    .font(.system(size: 12, weight: .semibold, design: .rounded))
                    .foregroundStyle(.white.opacity(0.9))

                Picker("Valittu kriteeri", selection: bindingForPromptSelection) {
                    ForEach(store.prompts) { prompt in
                        Text(prompt.title).tag(prompt.promptId)
                    }
                }
                .labelsHidden()
                .pickerStyle(.menu)
                .tint(.white)

                Text(store.selectedPrompt(for: exercise)?.title ?? "Valitse kriteeri")
                    .font(.system(size: 12, weight: .medium, design: .rounded))
                    .foregroundStyle(.white.opacity(0.74))
                    .lineLimit(2)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }

            Spacer(minLength: 0)

            Button {
                store.selectExercise(exercise)
                Task { await store.gradeExercise(exercise) }
            } label: {
                HStack(spacing: 8) {
                    Image(systemName: store.isGrading(exercise) ? "hourglass" : "play.fill")
                    Text(
                        store.isGrading(exercise)
                            ? "Arvioidaan..."
                            : "Aloita arviointi"
                    )
                        .lineLimit(1)
                }
                .frame(maxWidth: .infinity)
            }
            .buttonStyle(LiquidGlassButtonStyle(tint: Color(hex: "#6F937C")))
            .disabled(store.isGrading(exercise) || !store.hasPrompts)
        }
        .background(
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .fill(store.isSelected(exercise) ? Color(hex: "#4A535C").opacity(0.34) : Color(hex: "#2D343B").opacity(0.28))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .stroke(
                    store.isSelected(exercise) ? Color.white.opacity(0.18) : Color.white.opacity(0.08),
                    lineWidth: store.isSelected(exercise) ? 1.3 : 1
                )
        )
        .padding(18)
        .contentShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
        .onTapGesture {
            store.selectExercise(exercise)
        }
    }

    private var bindingForPromptSelection: Binding<String> {
        Binding(
            get: {
                store.selectedPromptByColumn[exercise.columnKey] ?? store.prompts.first?.promptId ?? ""
            },
            set: { newValue in
                store.setPrompt(newValue, for: exercise.columnKey)
            }
        )
    }
}

struct AutopilotPageView: View {
    @EnvironmentObject private var store: GuiStore
    let compact: Bool

    var body: some View {
        IntegratedPageSurface {
            VStack(alignment: .leading, spacing: 16) {
                HStack(alignment: .top, spacing: 16) {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Autopilot")
                            .font(.system(size: 22, weight: .bold, design: .rounded))
                            .foregroundStyle(.white)
                        Text("Rakenna tehtäväjono havaituista tehtävistä. Autopilot suorittaa ne tässä järjestyksessä yksi kerrallaan.")
                            .font(.system(size: 13, weight: .medium, design: .rounded))
                            .foregroundStyle(.white.opacity(0.76))
                    }

                    Spacer(minLength: 0)

                    HStack(spacing: 10) {
                        if store.autopilotRunning || store.gradingColumnKey != nil {
                            Button {
                                Task { await store.stopCurrentGrading() }
                            } label: {
                                Label("Pysäytä", systemImage: "stop.fill")
                            }
                            .buttonStyle(LiquidGlassButtonStyle(tint: Color(hex: "#8C7C78")))
                        }

                        Button {
                            Task { await store.startAutopilot() }
                        } label: {
                            Label(
                                store.autopilotRunning ? "Autopilot käynnissä..." : "Aloita",
                                systemImage: store.autopilotRunning ? "hourglass" : "play.fill"
                            )
                        }
                        .buttonStyle(LiquidGlassButtonStyle(tint: Color(hex: "#6F937C")))
                        .disabled(store.autopilotRunning || store.autopilotQueueExercises.isEmpty || !store.hasPrompts)
                    }
                }

                AdaptiveAxisStack(horizontal: !compact, spacing: 14) {
                    MiniInfoPill(label: "Jonossa", value: "\(store.autopilotQueueExercises.count)")
                    MiniInfoPill(label: "Saatavilla", value: "\(store.availableAutopilotExercises.count)")
                    MiniInfoPill(
                        label: "Tila",
                        value: store.autopilotRunning
                            ? "Autopilot arvioi nyt valittuja tehtäviä"
                            : (store.latestErrorMessage.map(store.redactedTextForDisplay) ?? store.displayedResultMessage)
                    )
                }

                Divider()
                    .overlay(Color.white.opacity(0.14))

                AdaptiveAxisStack(horizontal: !compact, spacing: 18) {
                    AutopilotAvailableExercisesPane(compact: compact)
                        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)

                    AutopilotQueuePane(compact: compact)
                        .frame(maxWidth: compact ? .infinity : 360, maxHeight: .infinity, alignment: .topLeading)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        }
    }
}

private struct AutopilotAvailableExercisesPane: View {
    @EnvironmentObject private var store: GuiStore
    let compact: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Havaitut tehtävät")
                    .font(.system(size: 17, weight: .bold, design: .rounded))
                    .foregroundStyle(.white)
                Spacer(minLength: 0)
                Text("Lisää jonoon yhdellä klikkauksella")
                    .font(.system(size: 11, weight: .medium, design: .rounded))
                    .foregroundStyle(.white.opacity(0.68))
            }

            if store.availableAutopilotExercises.isEmpty {
                EmptyStateView(
                    title: "Ei lisättäviä tehtäviä",
                    message: "Kun arvioimattomia tehtäviä havaitaan, ne ilmestyvät tähän tileinä. Jo jonossa olevat tehtävät poistuvat tästä näkymästä."
                )
                .frame(maxHeight: .infinity)
            } else {
                ScrollView {
                    LazyVGrid(
                        columns: [
                            GridItem(.adaptive(minimum: compact ? 210 : 230, maximum: compact ? 240 : 280), spacing: 14, alignment: .top)
                        ],
                        alignment: .leading,
                        spacing: 14
                    ) {
                        ForEach(store.availableAutopilotExercises) { exercise in
                            AutopilotSourceTile(exercise: exercise)
                                .frame(maxWidth: .infinity, minHeight: compact ? 214 : 232, alignment: .topLeading)
                        }
                    }
                    .padding(.bottom, 4)
                }
                .scrollIndicators(.hidden)
            }
        }
    }
}

private struct AutopilotSourceTile: View {
    @EnvironmentObject private var store: GuiStore
    let exercise: GuiExerciseColumn

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .top, spacing: 10) {
                VStack(alignment: .leading, spacing: 6) {
                    Text(exercise.title)
                        .font(.system(size: 16, weight: .bold, design: .rounded))
                        .foregroundStyle(.white)
                        .lineLimit(2)
                    if let categoryName = exercise.categoryName {
                        PromptTag(title: categoryName)
                    }
                }
                Spacer(minLength: 0)
                if let exerciseNumber = exercise.exerciseNumber {
                    PromptTag(title: "Tehtävä \(exerciseNumber)")
                }
            }

            ExerciseInfoLine(label: "Arvioimatta", value: "\(exercise.pendingCellCount) / \(exercise.totalCellCount)")

            VStack(alignment: .leading, spacing: 6) {
                Text("Kriteeri")
                    .font(.system(size: 12, weight: .semibold, design: .rounded))
                    .foregroundStyle(.white.opacity(0.9))
                Picker("Valittu kriteeri", selection: bindingForPromptSelection) {
                    ForEach(store.prompts) { prompt in
                        Text(prompt.title).tag(prompt.promptId)
                    }
                }
                .labelsHidden()
                .pickerStyle(.menu)
                .tint(.white)

                Text(store.selectedPrompt(for: exercise)?.title ?? "Valitse kriteeri")
                    .font(.system(size: 12, weight: .medium, design: .rounded))
                    .foregroundStyle(.white.opacity(0.74))
                    .lineLimit(2)
            }

            Spacer(minLength: 0)

            Button {
                store.enqueueAutopilotExercise(exercise)
            } label: {
                Label("Lisää jonoon", systemImage: "plus")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(LiquidGlassButtonStyle(tint: Color(hex: "#7E8A93")))
            .disabled(!store.hasPrompts)
        }
        .padding(18)
        .background(
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .fill(Color(hex: "#2D343B").opacity(0.28))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .stroke(Color.white.opacity(0.08), lineWidth: 1)
        )
    }

    private var bindingForPromptSelection: Binding<String> {
        Binding(
            get: {
                store.selectedPromptByColumn[exercise.columnKey] ?? store.prompts.first?.promptId ?? ""
            },
            set: { newValue in
                store.setPrompt(newValue, for: exercise.columnKey)
            }
        )
    }
}

private struct AutopilotQueuePane: View {
    @EnvironmentObject private var store: GuiStore
    let compact: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Suoritusjärjestys")
                    .font(.system(size: 17, weight: .bold, design: .rounded))
                    .foregroundStyle(.white)
                Spacer(minLength: 0)
                Text("\(store.autopilotQueueExercises.count) tehtävää")
                    .font(.system(size: 11, weight: .medium, design: .rounded))
                    .foregroundStyle(.white.opacity(0.68))
            }

            if store.autopilotQueueExercises.isEmpty {
                EmptyStateView(
                    title: "Autopilot-jono on tyhjä",
                    message: "Lisää tehtäviä vasemmalta. Jonossa olevia tilejä voi järjestää vetämällä niitä uuteen paikkaan."
                )
                .frame(maxHeight: .infinity)
            } else {
                ScrollView {
                    VStack(spacing: 12) {
                        ForEach(Array(store.autopilotQueueExercises.enumerated()), id: \.element.columnKey) { index, exercise in
                            AutopilotQueuedTile(exercise: exercise, position: index + 1)
                        }
                    }
                    .padding(.bottom, 4)
                }
                .scrollIndicators(.hidden)
            }
        }
    }
}

@MainActor
private struct AutopilotQueueDropDelegate: DropDelegate {
    let targetColumnKey: String
    let store: GuiStore

    func dropEntered(info: DropInfo) {
        guard let draggedKey = store.draggedAutopilotColumnKey else { return }
        store.moveAutopilotExercise(draggedKey, before: targetColumnKey)
    }

    func dropUpdated(info: DropInfo) -> DropProposal? {
        DropProposal(operation: .move)
    }

    func performDrop(info: DropInfo) -> Bool {
        store.draggedAutopilotColumnKey = nil
        return true
    }
}

private struct AutopilotQueuedTile: View {
    @EnvironmentObject private var store: GuiStore
    let exercise: GuiExerciseColumn
    let position: Int

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top, spacing: 10) {
                Text("\(position)")
                    .font(.system(size: 14, weight: .bold, design: .rounded))
                    .foregroundStyle(.white)
                    .frame(width: 28, height: 28)
                    .background(
                        RoundedRectangle(cornerRadius: 8, style: .continuous)
                            .fill(Color(hex: "#4A535C").opacity(0.40))
                    )

                VStack(alignment: .leading, spacing: 6) {
                    Text(exercise.title)
                        .font(.system(size: 15, weight: .bold, design: .rounded))
                        .foregroundStyle(.white)
                        .lineLimit(2)
                    Text(store.selectedPrompt(for: exercise)?.title ?? "Valitse kriteeri")
                        .font(.system(size: 12, weight: .medium, design: .rounded))
                        .foregroundStyle(.white.opacity(0.72))
                        .lineLimit(2)
                }

                Spacer(minLength: 0)

                Button {
                    store.removeAutopilotExercise(exercise.columnKey)
                } label: {
                    Image(systemName: "xmark")
                }
                .buttonStyle(CircularActionButtonStyle(tint: Color(hex: "#7E8A93")))
            }

            ExerciseInfoLine(label: "Arvioimatta", value: "\(exercise.pendingCellCount) / \(exercise.totalCellCount)")
        }
        .padding(16)
        .background(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .fill(
                    store.draggedAutopilotColumnKey == exercise.columnKey
                        ? Color(hex: "#4A535C").opacity(0.38)
                        : Color(hex: "#2D343B").opacity(0.28)
                )
        )
        .overlay(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .stroke(Color.white.opacity(0.08), lineWidth: 1)
        )
        .onDrag {
            store.draggedAutopilotColumnKey = exercise.columnKey
            return NSItemProvider(object: NSString(string: exercise.columnKey))
        }
        .onDrop(
            of: [UTType.text],
            delegate: AutopilotQueueDropDelegate(targetColumnKey: exercise.columnKey, store: store)
        )
    }
}

struct CriteriaPageView: View {
    let compact: Bool

    var body: some View {
        IntegratedPageSurface {
            GeometryReader { proxy in
                let libraryHeight = compact ? 300.0 : 320.0
                let workspaceMinHeight = compact ? 900.0 : 760.0

                ScrollView(.vertical) {
                    VStack(spacing: 14) {
                        PromptLibraryBrowserView(integrated: true)
                            .frame(height: libraryHeight)
                            .frame(maxWidth: .infinity)

                        PromptWorkspaceView(integrated: true)
                            .frame(maxWidth: .infinity, minHeight: workspaceMinHeight, alignment: .top)
                    }
                    .frame(width: proxy.size.width, alignment: .top)
                }
                .scrollIndicators(.visible)
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
            }
        }
    }
}
