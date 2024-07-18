import sqlalchemy
from montreal_forced_aligner.db import PathType
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import declarative_base, relationship

AnchorSqlBase = declarative_base()


class AcousticModel(AnchorSqlBase):
    __tablename__ = "acoustic_model"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False)
    path = Column(PathType, nullable=False, unique=True)
    available_locally = Column(Boolean, nullable=False, default=False)
    last_used = Column(DateTime, nullable=False, server_default=sqlalchemy.func.now(), index=True)

    corpora = relationship(
        "AnchorCorpus",
        back_populates="acoustic_model",
    )


class LanguageModel(AnchorSqlBase):
    __tablename__ = "language_model"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False)
    path = Column(PathType, nullable=False, unique=True)
    available_locally = Column(Boolean, nullable=False, default=False)
    last_used = Column(DateTime, nullable=False, server_default=sqlalchemy.func.now(), index=True)

    corpora = relationship(
        "AnchorCorpus",
        back_populates="language_model",
    )


class G2PModel(AnchorSqlBase):
    __tablename__ = "g2p_model"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False)
    path = Column(PathType, nullable=False, unique=True)
    available_locally = Column(Boolean, nullable=False, default=False)
    last_used = Column(DateTime, nullable=False, server_default=sqlalchemy.func.now(), index=True)

    corpora = relationship(
        "AnchorCorpus",
        back_populates="g2p_model",
    )


class Dictionary(AnchorSqlBase):
    __tablename__ = "dictionary"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False)
    path = Column(PathType, nullable=False, unique=True)
    available_locally = Column(Boolean, nullable=False, default=False)
    last_used = Column(DateTime, nullable=False, server_default=sqlalchemy.func.now(), index=True)

    corpora = relationship(
        "AnchorCorpus",
        back_populates="dictionary",
    )


class IvectorExtractor(AnchorSqlBase):
    __tablename__ = "ivector_extractor"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False)
    path = Column(PathType, nullable=False, unique=True)
    available_locally = Column(Boolean, nullable=False, default=False)
    last_used = Column(DateTime, nullable=False, server_default=sqlalchemy.func.now(), index=True)

    corpora = relationship(
        "AnchorCorpus",
        back_populates="ivector_extractor",
    )


class SadModel(AnchorSqlBase):
    __tablename__ = "sad_model"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False)
    path = Column(PathType, nullable=False, unique=True)
    available_locally = Column(Boolean, nullable=False, default=False)
    last_used = Column(DateTime, nullable=False, server_default=sqlalchemy.func.now(), index=True)

    corpora = relationship(
        "AnchorCorpus",
        back_populates="sad_model",
    )


class AnchorCorpus(AnchorSqlBase):
    __tablename__ = "corpus"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False, index=True)
    path = Column(PathType, nullable=False, index=True, unique=True)
    custom_mapping_path = Column(PathType, nullable=True)
    reference_directory = Column(PathType, nullable=True)
    current = Column(Boolean, nullable=False, default=False, index=True)
    # last_used = Column(DateTime, nullable=False, server_default=sqlalchemy.func.now(), index=True)

    acoustic_model_id = Column(Integer, ForeignKey("acoustic_model.id"), index=True, nullable=True)
    acoustic_model = relationship("AcousticModel", back_populates="corpora")

    language_model_id = Column(Integer, ForeignKey("language_model.id"), index=True, nullable=True)
    language_model = relationship("LanguageModel", back_populates="corpora")

    dictionary_id = Column(Integer, ForeignKey("dictionary.id"), index=True, nullable=True)
    dictionary = relationship("Dictionary", back_populates="corpora")

    g2p_model_id = Column(Integer, ForeignKey("g2p_model.id"), index=True, nullable=True)
    g2p_model = relationship("G2PModel", back_populates="corpora")

    ivector_extractor_id = Column(
        Integer, ForeignKey("ivector_extractor.id"), index=True, nullable=True
    )
    ivector_extractor = relationship("IvectorExtractor", back_populates="corpora")

    sad_model_id = Column(Integer, ForeignKey("sad_model.id"), index=True, nullable=True)
    sad_model = relationship("SadModel", back_populates="corpora")


MODEL_TYPES = {
    "acoustic": AcousticModel,
    "g2p": G2PModel,
    "dictionary": Dictionary,
    "language_model": LanguageModel,
    "ivector": IvectorExtractor,
    "sad": SadModel,
}
