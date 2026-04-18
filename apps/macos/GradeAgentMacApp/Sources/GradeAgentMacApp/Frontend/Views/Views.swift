import SwiftUI

// MARK: - Design tokens

enum Theme {
    // Backgrounds
    static let background = Color(hex: "#F5F1EA")      // warm cream
    static let backgroundEdge = Color(hex: "#ECE6DB")  // slightly deeper cream for depth
    static let surface = Color(hex: "#FFFFFF")         // paper white
    static let surfaceAlt = Color(hex: "#F9F5EE")      // cream tint for inset fields
    static let surfaceSidebar = Color(hex: "#EFE9DC")  // sidebar column tint

    // Ink / text
    static let ink = Color(hex: "#1C2430")             // near-black, cool charcoal
    static let inkMuted = Color(hex: "#5E6773")        // body copy
    static let inkSoft = Color(hex: "#8A93A0")         // labels, captions

    // Accents
    static let accent = Color(hex: "#2F6B4F")          // sage — primary CTA
    static let accentInk = Color(hex: "#1F4A37")       // darker sage for hover/press
    static let warning = Color(hex: "#B8654A")         // terracotta — stop/destructive
    static let neutral = Color(hex: "#5E6773")         // neutral CTA (same as inkMuted)
    static let highlight = Color(hex: "#C9A96A")       // warm ochre — selection/focus

    // Hairlines & shadows
    static let hairline = Color(hex: "#1C2430").opacity(0.10)
    static let hairlineSoft = Color(hex: "#1C2430").opacity(0.06)
    static let shadow = Color(hex: "#1C2430").opacity(0.08)
}

// MARK: - Background

struct LiquidGlassBackground: View {
    var body: some View {
        LinearGradient(
            colors: [Theme.background, Theme.backgroundEdge],
            startPoint: .top,
            endPoint: .bottom
        )
        .ignoresSafeArea()
    }
}

// Kept for compatibility; now renders a subtle paper header band instead of the metal overlay.
struct HeroImageOverlayView: View {
    var body: some View {
        LinearGradient(
            colors: [
                Theme.backgroundEdge.opacity(0.55),
                Theme.background.opacity(0.0),
            ],
            startPoint: .top,
            endPoint: .bottom
        )
        .overlay(alignment: .bottom) {
            Rectangle()
                .fill(Theme.hairlineSoft)
                .frame(height: 1)
        }
    }
}

// MARK: - Cards & surfaces

struct GlassCard<Content: View>: View {
    let padding: CGFloat
    let fillOpacity: Double
    let strokeOpacity: Double
    @ViewBuilder var content: Content

    init(
        padding: CGFloat = 20,
        fillOpacity: Double = 1.0,
        strokeOpacity: Double = 1.0,
        @ViewBuilder content: () -> Content
    ) {
        self.padding = padding
        self.fillOpacity = fillOpacity
        self.strokeOpacity = strokeOpacity
        self.content = content()
    }

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .fill(Theme.surface)

            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .stroke(Theme.hairline, lineWidth: 1)

            content
                .padding(padding)
        }
        .shadow(color: Theme.shadow, radius: 12, x: 0, y: 6)
    }
}

struct WorkspaceShell<Content: View>: View {
    @ViewBuilder var content: Content

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .fill(Theme.surface)

            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .stroke(Theme.hairline, lineWidth: 1)

            content
        }
        .shadow(color: Theme.shadow, radius: 14, x: 0, y: 8)
    }
}

struct IntegratedPageSurface<Content: View>: View {
    @ViewBuilder var content: Content

    var body: some View {
        content
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            .padding(.horizontal, 4)
            .padding(.vertical, 4)
    }
}

// MARK: - Adaptive layout

struct AdaptiveAxisStack<Content: View>: View {
    let horizontal: Bool
    let alignment: HorizontalAlignment
    let spacing: CGFloat
    @ViewBuilder var content: Content

    init(
        horizontal: Bool,
        alignment: HorizontalAlignment = .leading,
        spacing: CGFloat = 12,
        @ViewBuilder content: () -> Content
    ) {
        self.horizontal = horizontal
        self.alignment = alignment
        self.spacing = spacing
        self.content = content()
    }

    var body: some View {
        Group {
            if horizontal {
                HStack(alignment: .top, spacing: spacing) {
                    content
                }
            } else {
                VStack(alignment: alignment, spacing: spacing) {
                    content
                }
            }
        }
    }
}

// MARK: - Buttons

struct LiquidGlassButtonStyle: ButtonStyle {
    let tint: Color

    func makeBody(configuration: Configuration) -> some View {
        let resolvedTint = Theme.resolveButtonTint(tint)
        configuration.label
            .font(.system(size: 12, weight: .bold, design: .rounded))
            .foregroundStyle(Color.white)
            .padding(.horizontal, 16)
            .padding(.vertical, 10)
            .background(
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .fill(resolvedTint.opacity(configuration.isPressed ? 0.80 : 1.0))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .stroke(resolvedTint.opacity(0.0), lineWidth: 0)
            )
            .scaleEffect(configuration.isPressed ? 0.985 : 1)
            .shadow(color: Theme.shadow.opacity(configuration.isPressed ? 0.0 : 1.0), radius: 6, x: 0, y: 3)
            .animation(.easeOut(duration: 0.12), value: configuration.isPressed)
    }
}

struct CircularActionButtonStyle: ButtonStyle {
    let tint: Color

    func makeBody(configuration: Configuration) -> some View {
        let resolvedTint = Theme.resolveButtonTint(tint)
        configuration.label
            .font(.system(size: 13, weight: .bold))
            .foregroundStyle(Color.white)
            .frame(width: 34, height: 34)
            .background(
                Circle()
                    .fill(resolvedTint.opacity(configuration.isPressed ? 0.80 : 1.0))
            )
            .shadow(color: Theme.shadow.opacity(configuration.isPressed ? 0.0 : 1.0), radius: 5, x: 0, y: 3)
            .scaleEffect(configuration.isPressed ? 0.96 : 1)
            .animation(.easeOut(duration: 0.12), value: configuration.isPressed)
    }
}

extension Theme {
    /// Maps legacy per-call tint hexes (greens, warm-browns, greys) to the Soft Paper palette
    /// so existing call sites keep working without being rewritten.
    static func resolveButtonTint(_ color: Color) -> Color {
        // Greens in old palette → sage accent
        if color == Color(hex: "#6F937C")
            || color == Color(hex: "#7F9889")
            || color == Color(hex: "#7A8D83")
            || color == Color(hex: "#7E9487")
        {
            return Theme.accent
        }
        // Warm reds/browns → terracotta warning
        if color == Color(hex: "#8C7C78")
            || color == Color(hex: "#9A7B7B")
            || color == Color(hex: "#A08A78")
        {
            return Theme.warning
        }
        // Neutrals / greys → slate neutral
        if color == Color(hex: "#7E8A93")
            || color == Color(hex: "#8D939B")
            || color == Color(hex: "#8A939C")
        {
            return Theme.neutral
        }
        return color
    }
}

// MARK: - Sidebar

struct SidebarPanel<Content: View>: View {
    @ViewBuilder var content: Content

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .fill(Theme.surfaceSidebar)
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .stroke(Theme.hairlineSoft, lineWidth: 1)
            content
        }
        .shadow(color: Theme.shadow.opacity(0.6), radius: 10, x: 0, y: 4)
    }
}

struct SidebarGlyph: View {
    var body: some View {
        HStack(spacing: 6) {
            VStack(spacing: 6) {
                RoundedRectangle(cornerRadius: 4, style: .continuous)
                    .fill(Theme.ink)
                    .frame(width: 16, height: 16)
                RoundedRectangle(cornerRadius: 4, style: .continuous)
                    .stroke(Theme.ink.opacity(0.45), lineWidth: 1.4)
                    .frame(width: 16, height: 16)
            }
            VStack(spacing: 6) {
                RoundedRectangle(cornerRadius: 4, style: .continuous)
                    .stroke(Theme.ink.opacity(0.45), lineWidth: 1.4)
                    .frame(width: 16, height: 16)
                RoundedRectangle(cornerRadius: 4, style: .continuous)
                    .fill(Theme.accent)
                    .frame(width: 16, height: 16)
            }
        }
        .padding(.top, 4)
    }
}

struct SidebarNavigationSection<Content: View>: View {
    let title: String
    @ViewBuilder var content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            SidebarSectionTitle(title: title)
            content
        }
    }
}

struct SidebarSectionTitle: View {
    let title: String

    var body: some View {
        Text(title.uppercased())
            .font(.system(size: 10, weight: .heavy, design: .rounded))
            .foregroundStyle(Theme.inkSoft)
            .tracking(1.2)
    }
}

struct SidebarButton: View {
    let title: String
    let systemImage: String
    let selected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 10) {
                // Left accent bar indicates selection
                Rectangle()
                    .fill(selected ? Theme.accent : Color.clear)
                    .frame(width: 3)
                    .clipShape(RoundedRectangle(cornerRadius: 1.5, style: .continuous))

                Image(systemName: systemImage)
                    .font(.system(size: 13, weight: selected ? .bold : .semibold))
                    .frame(width: 18)
                    .foregroundStyle(selected ? Theme.ink : Theme.inkMuted)

                Text(title)
                    .font(.system(size: 13.5, weight: selected ? .bold : .medium, design: .rounded))
                    .foregroundStyle(selected ? Theme.ink : Theme.inkMuted)

                Spacer(minLength: 0)
            }
            .padding(.leading, 4)
            .padding(.trailing, 10)
            .padding(.vertical, 8)
            .background(
                RoundedRectangle(cornerRadius: 8, style: .continuous)
                    .fill(selected ? Theme.surface : Color.clear)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 8, style: .continuous)
                    .stroke(selected ? Theme.hairlineSoft : Color.clear, lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Hero dashboard pills

struct OverviewMetric: View {
    let label: String
    let value: String

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label.uppercased())
                .font(.system(size: 10, weight: .heavy, design: .rounded))
                .foregroundStyle(Theme.inkSoft)
                .tracking(0.8)
            Text(value)
                .font(.system(size: 15, weight: .bold, design: .rounded))
                .foregroundStyle(Theme.ink)
        }
        .padding(.vertical, 8)
    }
}

struct HeroDashboardView: View {
    @EnvironmentObject private var store: GuiStore
    let compact: Bool

    var body: some View {
        AdaptiveAxisStack(horizontal: !compact, spacing: compact ? 12 : 18) {
            VStack(alignment: .leading, spacing: 10) {
                Text(store.welcomeTitle)
                    .font(.system(size: compact ? 28 : 32, weight: .bold, design: .rounded))
                    .foregroundStyle(Theme.ink)

                Text("Sanoman kokeiden arviointityötila.")
                    .font(.system(size: 13, weight: .medium, design: .rounded))
                    .foregroundStyle(Theme.inkMuted)

                ViewThatFits(in: .horizontal) {
                    HStack(spacing: 10) {
                        HeroStatPill(label: "Selaimen tila", value: store.browserReady ? "Auki" : "Ei auki")
                        HeroStatPill(label: "Tehtävät", value: "\(store.detectedExerciseCount)")
                        HeroStatPill(label: "Kriteerit", value: "\(store.prompts.count)")
                        HeroStatPill(label: "Ryhmä", value: store.overview?.groupName ?? "-")
                    }

                    Grid(alignment: .leading, horizontalSpacing: 8, verticalSpacing: 8) {
                        GridRow {
                            HeroStatPill(label: "Selaimen tila", value: store.browserReady ? "Auki" : "Ei auki")
                            HeroStatPill(label: "Tehtävät", value: "\(store.detectedExerciseCount)")
                        }
                        GridRow {
                            HeroStatPill(label: "Kriteerit", value: "\(store.prompts.count)")
                            HeroStatPill(label: "Ryhmä", value: store.overview?.groupName ?? "-")
                        }
                    }
                }
            }
            .frame(maxWidth: compact ? .infinity : 720, alignment: .leading)

            if store.selectedPage == .ohjaus {
                AdaptiveAxisStack(horizontal: !compact, spacing: 10) {
                    HStack(spacing: 10) {
                        Button {
                            Task { await store.startBrowser() }
                        } label: {
                            Image(systemName: "play.fill")
                        }
                        .help("Käynnistä selain")
                        .buttonStyle(CircularActionButtonStyle(tint: Theme.accent))
                        .disabled(store.isStartingBrowser || store.browserReady)

                        Button {
                            Task { await store.stopBrowser() }
                        } label: {
                            Image(systemName: "stop.fill")
                        }
                        .help("Pysäytä selain")
                        .buttonStyle(CircularActionButtonStyle(tint: Theme.warning))
                        .disabled(!store.browserReady)
                    }

                    Button {
                        Task { await store.stopCurrentGrading() }
                    } label: {
                        Label(
                            store.isStopGradingRequested ? "Pysäytetään arviointi..." : "Pysäytä arviointi",
                            systemImage: store.isStopGradingRequested ? "hourglass" : "pause.circle.fill"
                        )
                    }
                    .buttonStyle(LiquidGlassButtonStyle(tint: Theme.warning))
                    .disabled(store.gradingColumnKey == nil || store.isStopGradingRequested)
                }
                .frame(maxWidth: compact ? .infinity : nil, alignment: compact ? .leading : .trailing)
                .padding(.top, compact ? 0 : 4)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

struct HeroStatPill: View {
    let label: String
    let value: String

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(label.uppercased())
                .font(.system(size: 10, weight: .heavy, design: .rounded))
                .foregroundStyle(Theme.inkSoft)
                .tracking(0.8)

            Text(value)
                .font(.system(size: 14, weight: .bold, design: .rounded))
                .foregroundStyle(Theme.ink)
                .lineLimit(1)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
        .frame(minWidth: 118, alignment: .leading)
        .background(Theme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .stroke(Theme.hairline, lineWidth: 1)
        )
        .shadow(color: Theme.shadow.opacity(0.5), radius: 4, x: 0, y: 2)
    }
}

struct MiniInfoPill: View {
    let label: String
    let value: String

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label.uppercased())
                .font(.system(size: 10, weight: .heavy, design: .rounded))
                .foregroundStyle(Theme.inkSoft)
                .tracking(0.8)

            Text(value)
                .font(.system(size: 12, weight: .semibold, design: .rounded))
                .foregroundStyle(Theme.ink)
                .lineLimit(2)
                .multilineTextAlignment(.leading)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
        .background(Theme.surfaceAlt)
        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .stroke(Theme.hairlineSoft, lineWidth: 1)
        )
    }
}

struct PromptPreviewView: View {
    let prompt: GuiPromptTemplate?

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Kriteerin esikatselu")
                .font(.system(size: 12, weight: .semibold, design: .rounded))
                .foregroundStyle(Theme.ink)

            ScrollView {
                Text(prompt?.body ?? "Valitse ensin kriteeri Kriteerit-kirjastosta.")
                    .font(.system(size: 12, weight: .medium, design: .rounded))
                    .foregroundStyle(Theme.inkMuted)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .textSelection(.enabled)
            }
            .frame(minHeight: 120, maxHeight: 150)
            .padding(14)
            .background(Theme.surfaceAlt)
            .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .stroke(Theme.hairlineSoft, lineWidth: 1)
            )
        }
    }
}

struct ExerciseInfoLine: View {
    let label: String
    let value: String

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label.uppercased())
                .font(.system(size: 10, weight: .heavy, design: .rounded))
                .foregroundStyle(Theme.inkSoft)
                .tracking(0.8)

            Text(value)
                .font(.system(size: 13, weight: .semibold, design: .rounded))
                .foregroundStyle(Theme.ink)
                .lineLimit(2)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.surfaceAlt)
        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .stroke(Theme.hairlineSoft, lineWidth: 1)
        )
    }
}

// MARK: - Prompt library

struct PromptLibraryBrowserView: View {
    @EnvironmentObject private var store: GuiStore
    @State private var builtInExpanded = true
    @State private var customExpanded = true
    let integrated: Bool

    private let contentInset: CGFloat = 4

    var body: some View {
        LibraryPanelShell(integrated: integrated) {
            VStack(spacing: 0) {
                HStack {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Kirjasto")
                            .font(.system(size: 18, weight: .bold, design: .rounded))
                            .foregroundStyle(Theme.ink)
                        Text("Valitse prompti listasta ja muokkaa sitä alapuolella.")
                            .font(.system(size: 12, weight: .medium, design: .rounded))
                            .foregroundStyle(Theme.inkMuted)
                    }

                    Spacer(minLength: 0)

                    Button {
                        Task { await store.createPrompt() }
                    } label: {
                        Label("Uusi kriteeri", systemImage: "plus")
                    }
                    .buttonStyle(LiquidGlassButtonStyle(tint: Theme.neutral))
                }
                .padding(.horizontal, contentInset)
                .padding(.top, contentInset)
                .padding(.bottom, 12)

                Divider()
                    .overlay(Theme.hairlineSoft)

                List(selection: promptSelectionBinding) {
                    DisclosureGroup(isExpanded: $builtInExpanded) {
                        ForEach(store.filteredBuiltInPrompts) { prompt in
                            PromptBrowserListRow(prompt: prompt)
                                .tag(Optional(prompt.promptId))
                        }
                    } label: {
                        PromptDirectoryHeader(title: "Oletuskriteerit", count: store.filteredBuiltInPrompts.count)
                    }

                    DisclosureGroup(isExpanded: $customExpanded) {
                        ForEach(store.filteredCustomPrompts) { prompt in
                            PromptBrowserListRow(prompt: prompt)
                                .tag(Optional(prompt.promptId))
                        }
                    } label: {
                        PromptDirectoryHeader(title: "Mukautetut kriteerit", count: store.filteredCustomPrompts.count)
                    }
                }
                .scrollContentBackground(.hidden)
                .listStyle(.sidebar)
                .searchable(text: $store.promptSearchText, prompt: "Hae kriteeriä")
                .background(Theme.surfaceAlt)
                .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: 12, style: .continuous)
                        .stroke(Theme.hairlineSoft, lineWidth: 1)
                )
                .padding(.top, 10)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        }
    }

    private var promptSelectionBinding: Binding<String?> {
        Binding(
            get: { store.selectedLibraryPromptId },
            set: { store.selectLibraryPrompt($0) }
        )
    }
}

struct PromptWorkspaceView: View {
    @EnvironmentObject private var store: GuiStore
    @FocusState private var editorFocused: Bool
    let integrated: Bool
    private let contentInset: CGFloat = 4

    private var selectedPrompt: GuiPromptTemplate? {
        store.selectedPromptFromLibrary
    }

    private var hasDraft: Bool {
        selectedPrompt != nil || !store.draftPromptTitle.isEmpty || !store.draftPromptBody.isEmpty
    }

    private var hasUnsavedChanges: Bool {
        guard let selectedPrompt else {
            return !store.draftPromptTitle.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                || !store.draftPromptBody.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        }
        return selectedPrompt.title != store.draftPromptTitle
            || selectedPrompt.body != store.draftPromptBody
            || selectedPrompt.modelProvider != store.draftPromptModelProvider
            || selectedPrompt.modelName != store.draftPromptModelName
            || selectedPrompt.reasoningLevel != store.draftPromptReasoningLevel
    }

    private var promptLineCount: Int {
        let trimmedBody = store.draftPromptBody.trimmingCharacters(in: .newlines)
        guard !trimmedBody.isEmpty else { return 1 }
        return trimmedBody.components(separatedBy: .newlines).count
    }

    private var detectedPlaceholders: [String] {
        [
            "(STUDENT)",
            "(PROGRESSION)",
            "(OBJECTIVE)",
            "(TARGET)",
            "(ANSWER)",
            "(MODELANSWER)",
            "(MAXPOINTS)",
            "(GROUP)",
            "(STUDENTS)",
            "(CATEGORY)",
            "(EXERCISE NUMBER)",
            "(SWE PHRASE)",
            "(FIN ANSWER)",
        ]
        .filter { store.draftPromptBody.localizedCaseInsensitiveContains($0) }
    }

    private var availableModelOptions: [PromptModelOption] {
        var options = PromptEditorOptions.modelOptions
        let currentID = "\(store.draftPromptModelProvider)|\(store.draftPromptModelName)"
        if !options.contains(where: { $0.id == currentID }),
           !store.draftPromptModelProvider.isEmpty,
           !store.draftPromptModelName.isEmpty {
            options.insert(
                PromptModelOption(
                    provider: store.draftPromptModelProvider,
                    modelName: store.draftPromptModelName,
                    title: store.draftPromptModelName,
                    subtitle: store.draftPromptModelProvider
                ),
                at: 0
            )
        }
        return options
    }

    private var selectedModelOptionID: String {
        "\(store.draftPromptModelProvider)|\(store.draftPromptModelName)"
    }

    var body: some View {
        LibraryPanelShell(integrated: integrated) {
            VStack(alignment: .leading, spacing: 16) {
                HStack(alignment: .top, spacing: 16) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Työtila")
                            .font(.system(size: 20, weight: .bold, design: .rounded))
                            .foregroundStyle(Theme.ink)
                        Text("Muokkaa valittua kriteeriä suoraan tässä ikkunassa.")
                            .font(.system(size: 12, weight: .medium, design: .rounded))
                            .foregroundStyle(Theme.inkMuted)
                    }

                    Spacer(minLength: 0)

                    HStack(spacing: 8) {
                        PromptTag(title: store.draftPromptBuiltIn ? "Oletuskriteeri" : "Mukautettu")
                        if hasUnsavedChanges {
                            PromptTag(title: "Muokattu")
                        }

                        Button {
                            editorFocused = true
                        } label: {
                            Label("Muokkaa", systemImage: "square.and.pencil")
                        }
                        .buttonStyle(LiquidGlassButtonStyle(tint: Theme.neutral))

                        Button {
                            Task { await store.saveCurrentPrompt() }
                        } label: {
                            Label(store.isSavingPrompt ? "Tallennetaan..." : "Tallenna", systemImage: "checkmark")
                        }
                        .buttonStyle(LiquidGlassButtonStyle(tint: Theme.accent))
                        .disabled(store.isSavingPrompt || !store.canSavePrompt)
                    }
                }

                Divider()
                    .overlay(Theme.hairlineSoft)

                ViewThatFits(in: .horizontal) {
                    HStack(spacing: 10) {
                        WorkspaceStatCapsule(label: "Tyyppi", value: store.draftPromptBuiltIn ? "Oletus" : "Mukautettu")
                        WorkspaceStatCapsule(label: "Rivejä", value: "\(promptLineCount)")
                        WorkspaceStatCapsule(label: "Merkkejä", value: "\(store.draftPromptBody.count)")
                        WorkspaceStatCapsule(label: "Paikkamerkkejä", value: "\(detectedPlaceholders.count)")
                    }

                    VStack(alignment: .leading, spacing: 8) {
                        WorkspaceStatCapsule(label: "Tyyppi", value: store.draftPromptBuiltIn ? "Oletus" : "Mukautettu")
                        WorkspaceStatCapsule(label: "Rivejä", value: "\(promptLineCount)")
                        WorkspaceStatCapsule(label: "Merkkejä", value: "\(store.draftPromptBody.count)")
                        WorkspaceStatCapsule(label: "Paikkamerkkejä", value: "\(detectedPlaceholders.count)")
                    }
                }

                if hasDraft {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Nimi")
                            .font(.system(size: 11, weight: .heavy, design: .rounded))
                            .foregroundStyle(Theme.inkSoft)
                            .tracking(0.8)

                        TextField("Anna kriteerille nimi", text: $store.draftPromptTitle)
                            .textFieldStyle(.plain)
                            .font(.system(size: 14, weight: .semibold, design: .rounded))
                            .foregroundStyle(Theme.ink)
                            .padding(.horizontal, 14)
                            .padding(.vertical, 12)
                            .background(Theme.surfaceAlt)
                            .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
                            .overlay(
                                RoundedRectangle(cornerRadius: 10, style: .continuous)
                                    .stroke(Theme.hairlineSoft, lineWidth: 1)
                            )
                    }

                    promptConfigurationSection

                    promptEditorCanvas
                        .frame(maxWidth: .infinity, minHeight: 620, alignment: .top)

                    VStack(alignment: .leading, spacing: 8) {
                        Text("Tuetut paikkamerkit")
                            .font(.system(size: 11, weight: .heavy, design: .rounded))
                            .foregroundStyle(Theme.inkSoft)
                            .tracking(0.8)

                        ScrollView(.horizontal) {
                            HStack(spacing: 8) {
                                if detectedPlaceholders.isEmpty {
                                    PromptTag(title: "Ei tunnistettuja paikkamerkkejä")
                                } else {
                                    ForEach(detectedPlaceholders, id: \.self) { placeholder in
                                        PromptTag(title: placeholder)
                                    }
                                }
                            }
                        }
                        .scrollIndicators(.hidden)

                        Text(store.promptPlaceholderHelp)
                            .font(.system(size: 11, weight: .medium, design: .rounded))
                            .foregroundStyle(Theme.inkMuted)
                    }
                } else {
                    EmptyStateView(
                        title: "Valitse kriteeri",
                        message: "Kun napsautat kirjastosta promptia, sen nimi ja sisältö avautuvat tähän työtilaan."
                    )
                    .frame(maxHeight: .infinity)
                }
            }
            .padding(contentInset)
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        }
    }

    private var promptConfigurationSection: some View {
        AdaptiveAxisStack(horizontal: true, spacing: 12) {
            VStack(alignment: .leading, spacing: 8) {
                Text("Arviointimalli")
                    .font(.system(size: 11, weight: .heavy, design: .rounded))
                    .foregroundStyle(Theme.inkSoft)
                    .tracking(0.8)

                Picker("Arviointimalli", selection: selectedModelBinding) {
                    ForEach(availableModelOptions) { option in
                        Text(option.displayName).tag(option.id)
                    }
                }
                .pickerStyle(.menu)
                .labelsHidden()
                .tint(Theme.ink)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(Theme.surfaceAlt)
                .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: 10, style: .continuous)
                        .stroke(Theme.hairlineSoft, lineWidth: 1)
                )

                if let option = availableModelOptions.first(where: { $0.id == selectedModelOptionID }) {
                    Text(option.displayName)
                        .font(.system(size: 11, weight: .medium, design: .rounded))
                        .foregroundStyle(Theme.inkMuted)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)

            VStack(alignment: .leading, spacing: 8) {
                Text("Reasoning-taso")
                    .font(.system(size: 11, weight: .heavy, design: .rounded))
                    .foregroundStyle(Theme.inkSoft)
                    .tracking(0.8)

                Picker("Reasoning-taso", selection: $store.draftPromptReasoningLevel) {
                    ForEach(PromptEditorOptions.reasoningOptions) { option in
                        Text("\(option.title) - \(option.subtitle)").tag(option.value)
                    }
                }
                .pickerStyle(.menu)
                .labelsHidden()
                .tint(Theme.ink)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(Theme.surfaceAlt)
                .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: 10, style: .continuous)
                        .stroke(Theme.hairlineSoft, lineWidth: 1)
                )

                if let option = PromptEditorOptions.reasoningOptions.first(where: { $0.value == store.draftPromptReasoningLevel }) {
                    Text(option.subtitle)
                        .font(.system(size: 11, weight: .medium, design: .rounded))
                        .foregroundStyle(Theme.inkMuted)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private var selectedModelBinding: Binding<String> {
        Binding(
            get: { selectedModelOptionID },
            set: { newValue in
                guard let option = availableModelOptions.first(where: { $0.id == newValue }) else { return }
                store.draftPromptModelProvider = option.provider
                store.draftPromptModelName = option.modelName
            }
        )
    }

    private var promptEditorCanvas: some View {
        WorkspaceCanvas(title: "Muokkaus", subtitle: "Kirjoita, tarkista ja viimeistele arviointikriteeri tässä.") {
            TextEditor(text: $store.draftPromptBody)
                .focused($editorFocused)
                .font(.system(size: 13, weight: .medium, design: .monospaced))
                .scrollContentBackground(.hidden)
                .padding(14)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(Theme.surfaceAlt)
                .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: 12, style: .continuous)
                        .stroke(Theme.hairlineSoft, lineWidth: 1)
                )
                .foregroundStyle(Theme.ink)
        }
    }
}

struct LibraryPanelShell<Content: View>: View {
    let integrated: Bool
    @ViewBuilder var content: Content

    init(integrated: Bool, @ViewBuilder content: () -> Content) {
        self.integrated = integrated
        self.content = content()
    }

    var body: some View {
        Group {
            if integrated {
                ZStack {
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .fill(Theme.surface)
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .stroke(Theme.hairlineSoft, lineWidth: 1)
                    content
                        .padding(18)
                }
                .shadow(color: Theme.shadow.opacity(0.5), radius: 8, x: 0, y: 3)
            } else {
                GlassCard {
                    content
                }
            }
        }
    }
}

struct PromptBrowserListRow: View {
    let prompt: GuiPromptTemplate

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: prompt.builtIn ? "doc.text.image.fill" : "square.and.pencil")
                .foregroundStyle(prompt.builtIn ? Theme.inkMuted : Theme.accent)
            VStack(alignment: .leading, spacing: 3) {
                Text(prompt.title)
                    .font(.system(size: 13, weight: .semibold, design: .rounded))
                    .foregroundStyle(Theme.ink)

                Text(prompt.builtIn ? "Oletuskriteeri" : "Mukautettu kriteeri")
                    .font(.system(size: 11, weight: .medium, design: .rounded))
                    .foregroundStyle(Theme.inkSoft)
            }
        }
        .padding(.vertical, 3)
    }
}

struct PromptDirectoryHeader: View {
    let title: String
    let count: Int

    var body: some View {
        HStack {
            Text(title)
                .font(.system(size: 12, weight: .bold, design: .rounded))
                .foregroundStyle(Theme.ink)
            Spacer(minLength: 0)
            Text("\(count)")
                .font(.system(size: 11, weight: .bold, design: .rounded))
                .foregroundStyle(Theme.inkSoft)
        }
    }
}

struct PromptTag: View {
    let title: String

    var body: some View {
        Text(title)
            .font(.system(size: 11, weight: .semibold, design: .rounded))
            .foregroundStyle(Theme.ink)
            .padding(.horizontal, 10)
            .padding(.vertical, 5)
            .background(Theme.surfaceAlt)
            .clipShape(Capsule(style: .continuous))
            .overlay(
                Capsule(style: .continuous)
                    .stroke(Theme.hairline, lineWidth: 1)
            )
    }
}

struct WorkspaceCanvas<Content: View>: View {
    let title: String
    let subtitle: String
    @ViewBuilder var content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            VStack(alignment: .leading, spacing: 4) {
                Text(title)
                    .font(.system(size: 14, weight: .bold, design: .rounded))
                    .foregroundStyle(Theme.ink)
                Text(subtitle)
                    .font(.system(size: 11, weight: .medium, design: .rounded))
                    .foregroundStyle(Theme.inkMuted)
            }

            content
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .padding(14)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(Theme.surfaceAlt)
        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(Theme.hairlineSoft, lineWidth: 1)
        )
    }
}

// MARK: - Settings

struct SettingsPageView: View {
    @EnvironmentObject private var store: GuiStore
    let compact: Bool

    var body: some View {
        IntegratedPageSurface {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Asetukset")
                            .font(.system(size: 24, weight: .bold, design: .rounded))
                            .foregroundStyle(Theme.ink)
                        Text("Sovelluksen näkymä- ja yksityisyysasetukset.")
                            .font(.system(size: 13, weight: .medium, design: .rounded))
                            .foregroundStyle(Theme.inkMuted)
                    }

                    SettingsSectionShell(
                        title: "Yksityisyys",
                        subtitle: "Käyttöliittymän tietosuojaan liittyvät asetukset."
                    ) {
                        SettingsToggleRow(
                            title: "Näytöstila",
                            subtitle: "Piilota opiskelijanimet käyttöliittymässä.",
                            isOn: $store.hideStudentNamesInGui
                        )
                    }
                }
                .frame(maxWidth: .infinity, alignment: .topLeading)
                .padding(.bottom, 8)
            }
            .scrollIndicators(.visible)
        }
    }
}

struct SettingsSectionShell<Content: View>: View {
    let title: String
    let subtitle: String
    @ViewBuilder var content: Content

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .fill(Theme.surface)
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .stroke(Theme.hairline, lineWidth: 1)
            VStack(alignment: .leading, spacing: 14) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(title)
                        .font(.system(size: 16, weight: .bold, design: .rounded))
                        .foregroundStyle(Theme.ink)
                    Text(subtitle)
                        .font(.system(size: 12, weight: .medium, design: .rounded))
                        .foregroundStyle(Theme.inkMuted)
                }

                content
            }
            .frame(maxWidth: .infinity, alignment: .topLeading)
            .padding(20)
        }
        .shadow(color: Theme.shadow.opacity(0.5), radius: 8, x: 0, y: 4)
    }
}

struct SettingsToggleRow: View {
    let title: String
    let subtitle: String
    @Binding var isOn: Bool

    var body: some View {
        HStack(alignment: .center, spacing: 16) {
            VStack(alignment: .leading, spacing: 4) {
                Text(title)
                    .font(.system(size: 14, weight: .bold, design: .rounded))
                    .foregroundStyle(Theme.ink)
                Text(subtitle)
                    .font(.system(size: 12, weight: .medium, design: .rounded))
                    .foregroundStyle(Theme.inkMuted)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Spacer(minLength: 0)

            Toggle(isOn: $isOn) {
                EmptyView()
            }
            .labelsHidden()
            .toggleStyle(.switch)
            .tint(Theme.accent)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
        .background(Theme.surfaceAlt)
        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .stroke(Theme.hairlineSoft, lineWidth: 1)
        )
    }
}

struct WorkspaceStatCapsule: View {
    let label: String
    let value: String

    var body: some View {
        LabeledContent {
            Text(value)
                .font(.system(size: 12, weight: .bold, design: .rounded))
                .foregroundStyle(Theme.ink)
        } label: {
            Text(label.uppercased())
                .font(.system(size: 10, weight: .heavy, design: .rounded))
                .foregroundStyle(Theme.inkSoft)
                .tracking(0.8)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
        .background(Theme.surfaceAlt)
        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .stroke(Theme.hairlineSoft, lineWidth: 1)
        )
    }
}

struct EmptyStateView: View {
    let title: String
    let message: String

    var body: some View {
        ContentUnavailableView {
            Label(title, systemImage: "sparkles.rectangle.stack")
                .foregroundStyle(Theme.ink)
        } description: {
            Text(message)
                .foregroundStyle(Theme.inkMuted)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

extension Color {
    init(hex: String) {
        let hexString = hex.trimmingCharacters(in: CharacterSet.alphanumerics.inverted)
        var int: UInt64 = 0
        Scanner(string: hexString).scanHexInt64(&int)
        let red, green, blue: UInt64
        switch hexString.count {
        case 6:
            (red, green, blue) = (int >> 16, int >> 8 & 0xFF, int & 0xFF)
        default:
            (red, green, blue) = (255, 255, 255)
        }
        self.init(
            .sRGB,
            red: Double(red) / 255.0,
            green: Double(green) / 255.0,
            blue: Double(blue) / 255.0,
            opacity: 1
        )
    }
}
